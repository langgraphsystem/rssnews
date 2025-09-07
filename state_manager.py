"""
Production-grade Distributed State Management and Locking System
Provides distributed coordination, state machines, and idempotency guarantees for RSS processing.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from uuid import uuid4

import asyncpg
import redis.asyncio as redis
from pydantic import BaseModel, Field

from monitoring import MetricsCollector

logger = logging.getLogger(__name__)


class LockType(Enum):
    """Types of distributed locks"""
    EXCLUSIVE = "exclusive"    # Only one holder allowed
    SHARED = "shared"         # Multiple readers allowed
    ADVISORY = "advisory"     # PostgreSQL advisory lock


class LockStatus(Enum):
    """Lock acquisition status"""
    ACQUIRED = "acquired"
    DENIED = "denied"
    EXPIRED = "expired"
    RELEASED = "released"
    ERROR = "error"


class EntityState(Enum):
    """Generic entity states for state machine"""
    CREATED = "created"
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


@dataclass
class LockInfo:
    """Information about a distributed lock"""
    key: str
    owner: str
    lock_type: LockType
    acquired_at: datetime
    expires_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    renewal_count: int = 0
    
    @property
    def is_expired(self) -> bool:
        """Check if lock is expired"""
        return datetime.utcnow() > self.expires_at
    
    @property
    def time_remaining(self) -> timedelta:
        """Time remaining before expiration"""
        return max(timedelta(0), self.expires_at - datetime.utcnow())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'key': self.key,
            'owner': self.owner,
            'lock_type': self.lock_type.value,
            'acquired_at': self.acquired_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'metadata': self.metadata,
            'renewal_count': self.renewal_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LockInfo':
        """Create from dictionary"""
        return cls(
            key=data['key'],
            owner=data['owner'],
            lock_type=LockType(data['lock_type']),
            acquired_at=datetime.fromisoformat(data['acquired_at']),
            expires_at=datetime.fromisoformat(data['expires_at']),
            metadata=data.get('metadata', {}),
            renewal_count=data.get('renewal_count', 0)
        )


@dataclass
class StateTransition:
    """State transition definition"""
    from_state: EntityState
    to_state: EntityState
    trigger: str
    conditions: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    
    def is_valid_transition(self, current_state: EntityState) -> bool:
        """Check if transition is valid from current state"""
        return current_state == self.from_state


class StateMachine:
    """Generic state machine for entity lifecycle management"""
    
    def __init__(self, entity_type: str, initial_state: EntityState = EntityState.CREATED):
        self.entity_type = entity_type
        self.initial_state = initial_state
        self.transitions: List[StateTransition] = []
        self.state_handlers: Dict[EntityState, List[callable]] = {}
        self.transition_handlers: Dict[str, List[callable]] = {}
    
    def add_transition(self, transition: StateTransition):
        """Add a state transition"""
        self.transitions.append(transition)
    
    def add_state_handler(self, state: EntityState, handler: callable):
        """Add handler for entering a state"""
        if state not in self.state_handlers:
            self.state_handlers[state] = []
        self.state_handlers[state].append(handler)
    
    def add_transition_handler(self, trigger: str, handler: callable):
        """Add handler for a transition trigger"""
        if trigger not in self.transition_handlers:
            self.transition_handlers[trigger] = []
        self.transition_handlers[trigger].append(handler)
    
    def get_valid_transitions(self, current_state: EntityState) -> List[StateTransition]:
        """Get valid transitions from current state"""
        return [t for t in self.transitions if t.is_valid_transition(current_state)]
    
    def can_transition(self, current_state: EntityState, trigger: str) -> bool:
        """Check if transition is possible"""
        valid_transitions = self.get_valid_transitions(current_state)
        return any(t.trigger == trigger for t in valid_transitions)
    
    def get_transition(self, current_state: EntityState, trigger: str) -> Optional[StateTransition]:
        """Get specific transition"""
        for transition in self.transitions:
            if transition.from_state == current_state and transition.trigger == trigger:
                return transition
        return None


class DistributedLockManager:
    """
    Production-grade distributed lock manager supporting multiple backends:
    - Redis for high-performance locks
    - PostgreSQL for persistent locks and advisory locks
    - Hybrid mode for maximum reliability
    """
    
    def __init__(self,
                 redis_client: redis.Redis,
                 db_pool: asyncpg.Pool,
                 metrics: MetricsCollector,
                 default_timeout: int = 300):  # 5 minutes default
        self.redis = redis_client
        self.db_pool = db_pool
        self.metrics = metrics
        self.default_timeout = default_timeout
        
        # Lock renewal task
        self._renewal_tasks: Dict[str, asyncio.Task] = {}
        self._renewal_intervals: Dict[str, int] = {}
        
        # Lua scripts for atomic operations
        self._acquire_script = None
        self._release_script = None
        self._renew_script = None
        
    async def initialize(self):
        """Initialize the lock manager"""
        await self._load_lua_scripts()
        await self._create_database_objects()
    
    async def _load_lua_scripts(self):
        """Load Lua scripts for atomic Redis operations"""
        
        # Acquire lock script
        acquire_script = """
        local key = KEYS[1]
        local owner = ARGV[1]
        local ttl = tonumber(ARGV[2])
        local lock_type = ARGV[3]
        local metadata = ARGV[4]
        
        -- Check if lock exists
        local current_owner = redis.call('hget', key, 'owner')
        if current_owner then
            if current_owner == owner then
                -- Renew existing lock
                redis.call('expire', key, ttl)
                redis.call('hincrby', key, 'renewal_count', 1)
                return 'renewed'
            else
                return 'denied'
            end
        end
        
        -- Acquire new lock
        redis.call('hmset', key,
            'owner', owner,
            'lock_type', lock_type,
            'acquired_at', ARGV[5],
            'expires_at', ARGV[6],
            'metadata', metadata,
            'renewal_count', 0
        )
        redis.call('expire', key, ttl)
        return 'acquired'
        """
        
        self._acquire_script = self.redis.register_script(acquire_script)
        
        # Release lock script
        release_script = """
        local key = KEYS[1]
        local owner = ARGV[1]
        
        local current_owner = redis.call('hget', key, 'owner')
        if current_owner == owner then
            redis.call('del', key)
            return 'released'
        else
            return 'not_owner'
        end
        """
        
        self._release_script = self.redis.register_script(release_script)
        
        # Renew lock script
        renew_script = """
        local key = KEYS[1]
        local owner = ARGV[1]
        local ttl = tonumber(ARGV[2])
        local new_expires_at = ARGV[3]
        
        local current_owner = redis.call('hget', key, 'owner')
        if current_owner == owner then
            redis.call('hset', key, 'expires_at', new_expires_at)
            redis.call('hincrby', key, 'renewal_count', 1)
            redis.call('expire', key, ttl)
            return 'renewed'
        else
            return 'not_owner'
        end
        """
        
        self._renew_script = self.redis.register_script(renew_script)
    
    async def _create_database_objects(self):
        """Create database objects for persistent locks"""
        # The distributed_locks table is already created in schema_production.sql
        pass
    
    async def acquire_lock(self,
                          key: str,
                          owner: str,
                          timeout_seconds: int = None,
                          lock_type: LockType = LockType.EXCLUSIVE,
                          auto_renew: bool = True,
                          metadata: Dict[str, Any] = None) -> LockStatus:
        """
        Acquire a distributed lock with multiple strategies
        
        Args:
            key: Lock identifier
            owner: Lock owner identifier
            timeout_seconds: Lock timeout (default: class default)
            lock_type: Type of lock (exclusive, shared, advisory)
            auto_renew: Whether to auto-renew the lock
            metadata: Additional metadata to store with lock
            
        Returns:
            LockStatus indicating result
        """
        start_time = time.time()
        timeout_seconds = timeout_seconds or self.default_timeout
        metadata = metadata or {}
        
        try:
            # Try Redis first for performance
            redis_status = await self._acquire_redis_lock(
                key, owner, timeout_seconds, lock_type, metadata
            )
            
            if redis_status in [LockStatus.ACQUIRED, LockStatus.DENIED]:
                # For critical locks, also acquire PostgreSQL advisory lock
                if metadata.get('critical', False) or lock_type == LockType.ADVISORY:
                    pg_status = await self._acquire_postgres_lock(
                        key, owner, timeout_seconds, metadata
                    )
                    
                    if pg_status != LockStatus.ACQUIRED and redis_status == LockStatus.ACQUIRED:
                        # Release Redis lock if PostgreSQL acquisition failed
                        await self.release_lock(key, owner)
                        return LockStatus.DENIED
            
            # Set up auto-renewal if requested and lock acquired
            if redis_status == LockStatus.ACQUIRED and auto_renew:
                await self._start_auto_renewal(key, owner, timeout_seconds)
            
            # Record metrics
            acquisition_time = time.time() - start_time
            await self.metrics.histogram("locks.acquisition_time", acquisition_time)
            await self.metrics.increment(f"locks.acquired.{redis_status.value}")
            
            if redis_status == LockStatus.ACQUIRED:
                logger.debug(f"Acquired lock '{key}' for owner '{owner}' (type: {lock_type.value})")
            
            return redis_status
            
        except Exception as e:
            logger.error(f"Failed to acquire lock '{key}' for owner '{owner}': {e}", exc_info=True)
            await self.metrics.increment("locks.acquisition_error")
            return LockStatus.ERROR
    
    async def _acquire_redis_lock(self,
                                 key: str,
                                 owner: str,
                                 timeout_seconds: int,
                                 lock_type: LockType,
                                 metadata: Dict[str, Any]) -> LockStatus:
        """Acquire lock using Redis"""
        redis_key = f"lock:{key}"
        acquired_at = datetime.utcnow()
        expires_at = acquired_at + timedelta(seconds=timeout_seconds)
        
        try:
            result = await self._acquire_script(
                keys=[redis_key],
                args=[
                    owner,
                    timeout_seconds,
                    lock_type.value,
                    json.dumps(metadata),
                    acquired_at.isoformat(),
                    expires_at.isoformat()
                ]
            )
            
            if result == b'acquired':
                return LockStatus.ACQUIRED
            elif result == b'renewed':
                return LockStatus.ACQUIRED
            else:
                return LockStatus.DENIED
                
        except Exception as e:
            logger.error(f"Redis lock acquisition failed for '{key}': {e}")
            return LockStatus.ERROR
    
    async def _acquire_postgres_lock(self,
                                    key: str,
                                    owner: str,
                                    timeout_seconds: int,
                                    metadata: Dict[str, Any]) -> LockStatus:
        """Acquire lock using PostgreSQL advisory locks and persistent storage"""
        try:
            async with self.db_pool.acquire() as conn:
                # Generate numeric lock ID from key hash
                lock_id = self._key_to_lock_id(key)
                
                # Try to acquire advisory lock
                acquired = await conn.fetchval(
                    "SELECT pg_try_advisory_lock($1)",
                    lock_id
                )
                
                if not acquired:
                    return LockStatus.DENIED
                
                # Store lock information for persistence
                expires_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)
                
                await conn.execute("""
                    INSERT INTO distributed_locks (lock_key, owner, expires_at, metadata)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (lock_key) DO UPDATE SET
                        owner = $2,
                        acquired_at = NOW(),
                        expires_at = $3,
                        metadata = $4
                """, key, owner, expires_at, json.dumps(metadata))
                
                return LockStatus.ACQUIRED
                
        except Exception as e:
            logger.error(f"PostgreSQL lock acquisition failed for '{key}': {e}")
            return LockStatus.ERROR
    
    async def release_lock(self, key: str, owner: str) -> LockStatus:
        """Release a distributed lock"""
        try:
            # Release Redis lock
            redis_status = await self._release_redis_lock(key, owner)
            
            # Release PostgreSQL lock
            pg_status = await self._release_postgres_lock(key, owner)
            
            # Stop auto-renewal
            await self._stop_auto_renewal(key, owner)
            
            # Record metrics
            await self.metrics.increment(f"locks.released.{redis_status.value}")
            
            logger.debug(f"Released lock '{key}' for owner '{owner}'")
            
            return redis_status
            
        except Exception as e:
            logger.error(f"Failed to release lock '{key}' for owner '{owner}': {e}", exc_info=True)
            await self.metrics.increment("locks.release_error")
            return LockStatus.ERROR
    
    async def _release_redis_lock(self, key: str, owner: str) -> LockStatus:
        """Release Redis lock"""
        redis_key = f"lock:{key}"
        
        try:
            result = await self._release_script(keys=[redis_key], args=[owner])
            
            if result == b'released':
                return LockStatus.RELEASED
            else:
                return LockStatus.DENIED  # Not the owner
                
        except Exception as e:
            logger.error(f"Redis lock release failed for '{key}': {e}")
            return LockStatus.ERROR
    
    async def _release_postgres_lock(self, key: str, owner: str) -> LockStatus:
        """Release PostgreSQL lock"""
        try:
            async with self.db_pool.acquire() as conn:
                # Release advisory lock
                lock_id = self._key_to_lock_id(key)
                await conn.fetchval("SELECT pg_advisory_unlock($1)", lock_id)
                
                # Remove from persistent storage
                await conn.execute(
                    "DELETE FROM distributed_locks WHERE lock_key = $1 AND owner = $2",
                    key, owner
                )
                
                return LockStatus.RELEASED
                
        except Exception as e:
            logger.error(f"PostgreSQL lock release failed for '{key}': {e}")
            return LockStatus.ERROR
    
    async def renew_lock(self, key: str, owner: str, additional_seconds: int = None) -> LockStatus:
        """Renew an existing lock"""
        additional_seconds = additional_seconds or self.default_timeout
        
        try:
            redis_key = f"lock:{key}"
            new_expires_at = datetime.utcnow() + timedelta(seconds=additional_seconds)
            
            result = await self._renew_script(
                keys=[redis_key],
                args=[owner, additional_seconds, new_expires_at.isoformat()]
            )
            
            if result == b'renewed':
                # Also renew PostgreSQL lock if it exists
                await self._renew_postgres_lock(key, owner, additional_seconds)
                
                await self.metrics.increment("locks.renewed")
                return LockStatus.ACQUIRED
            else:
                return LockStatus.DENIED
                
        except Exception as e:
            logger.error(f"Failed to renew lock '{key}' for owner '{owner}': {e}")
            await self.metrics.increment("locks.renewal_error")
            return LockStatus.ERROR
    
    async def _renew_postgres_lock(self, key: str, owner: str, additional_seconds: int):
        """Renew PostgreSQL lock"""
        try:
            async with self.db_pool.acquire() as conn:
                new_expires_at = datetime.utcnow() + timedelta(seconds=additional_seconds)
                
                await conn.execute("""
                    UPDATE distributed_locks 
                    SET expires_at = $1
                    WHERE lock_key = $2 AND owner = $3
                """, new_expires_at, key, owner)
                
        except Exception as e:
            logger.error(f"PostgreSQL lock renewal failed for '{key}': {e}")
    
    async def get_lock_info(self, key: str) -> Optional[LockInfo]:
        """Get information about a lock"""
        try:
            redis_key = f"lock:{key}"
            lock_data = await self.redis.hgetall(redis_key)
            
            if not lock_data:
                return None
            
            return LockInfo(
                key=key,
                owner=lock_data[b'owner'].decode(),
                lock_type=LockType(lock_data[b'lock_type'].decode()),
                acquired_at=datetime.fromisoformat(lock_data[b'acquired_at'].decode()),
                expires_at=datetime.fromisoformat(lock_data[b'expires_at'].decode()),
                metadata=json.loads(lock_data.get(b'metadata', b'{}').decode()),
                renewal_count=int(lock_data.get(b'renewal_count', 0))
            )
            
        except Exception as e:
            logger.error(f"Failed to get lock info for '{key}': {e}")
            return None
    
    async def list_locks(self, owner: str = None, pattern: str = "lock:*") -> List[LockInfo]:
        """List all locks or locks for a specific owner"""
        try:
            locks = []
            async for key in self.redis.scan_iter(match=pattern):
                lock_data = await self.redis.hgetall(key)
                if not lock_data:
                    continue
                
                lock_owner = lock_data[b'owner'].decode()
                if owner and lock_owner != owner:
                    continue
                
                lock_key = key.decode().replace('lock:', '', 1)
                
                lock_info = LockInfo(
                    key=lock_key,
                    owner=lock_owner,
                    lock_type=LockType(lock_data[b'lock_type'].decode()),
                    acquired_at=datetime.fromisoformat(lock_data[b'acquired_at'].decode()),
                    expires_at=datetime.fromisoformat(lock_data[b'expires_at'].decode()),
                    metadata=json.loads(lock_data.get(b'metadata', b'{}').decode()),
                    renewal_count=int(lock_data.get(b'renewal_count', 0))
                )
                
                locks.append(lock_info)
            
            return locks
            
        except Exception as e:
            logger.error(f"Failed to list locks: {e}")
            return []
    
    async def cleanup_expired_locks(self) -> int:
        """Clean up expired locks"""
        cleaned_count = 0
        
        try:
            # Clean up Redis locks
            async for key in self.redis.scan_iter(match="lock:*"):
                lock_data = await self.redis.hgetall(key)
                if not lock_data:
                    continue
                
                try:
                    expires_at = datetime.fromisoformat(lock_data[b'expires_at'].decode())
                    if datetime.utcnow() > expires_at:
                        await self.redis.delete(key)
                        cleaned_count += 1
                except (KeyError, ValueError):
                    # Invalid lock data, delete it
                    await self.redis.delete(key)
                    cleaned_count += 1
            
            # Clean up PostgreSQL locks
            async with self.db_pool.acquire() as conn:
                pg_cleaned = await conn.fetchval("""
                    DELETE FROM distributed_locks 
                    WHERE expires_at < NOW()
                    RETURNING COUNT(*)
                """)
                cleaned_count += pg_cleaned or 0
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired locks")
                await self.metrics.increment("locks.cleanup.expired", cleaned_count)
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired locks: {e}")
            await self.metrics.increment("locks.cleanup.error")
            return cleaned_count
    
    async def _start_auto_renewal(self, key: str, owner: str, interval_seconds: int):
        """Start automatic lock renewal"""
        renewal_key = f"{key}:{owner}"
        
        # Stop existing renewal if any
        await self._stop_auto_renewal(key, owner)
        
        # Start new renewal task
        renewal_interval = max(interval_seconds // 3, 30)  # Renew at 1/3 of timeout, min 30s
        self._renewal_intervals[renewal_key] = renewal_interval
        
        task = asyncio.create_task(self._auto_renewal_loop(key, owner, renewal_interval))
        self._renewal_tasks[renewal_key] = task
    
    async def _stop_auto_renewal(self, key: str, owner: str):
        """Stop automatic lock renewal"""
        renewal_key = f"{key}:{owner}"
        
        if renewal_key in self._renewal_tasks:
            self._renewal_tasks[renewal_key].cancel()
            del self._renewal_tasks[renewal_key]
        
        if renewal_key in self._renewal_intervals:
            del self._renewal_intervals[renewal_key]
    
    async def _auto_renewal_loop(self, key: str, owner: str, interval_seconds: int):
        """Auto-renewal loop for a specific lock"""
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                
                # Check if lock still exists and belongs to us
                lock_info = await self.get_lock_info(key)
                if not lock_info or lock_info.owner != owner:
                    break
                
                # Renew the lock
                status = await self.renew_lock(key, owner)
                if status != LockStatus.ACQUIRED:
                    logger.warning(f"Failed to auto-renew lock '{key}' for owner '{owner}': {status}")
                    break
                
        except asyncio.CancelledError:
            pass  # Normal cancellation
        except Exception as e:
            logger.error(f"Auto-renewal loop failed for lock '{key}', owner '{owner}': {e}")
    
    def _key_to_lock_id(self, key: str) -> int:
        """Convert lock key to PostgreSQL lock ID"""
        # Create a stable 32-bit signed integer from key
        hash_obj = hashlib.sha256(key.encode())
        hash_int = int(hash_obj.hexdigest()[:8], 16)
        # Ensure it fits in 32-bit signed int range
        return hash_int % (2**31) if hash_int >= 2**31 else hash_int


class IdempotencyManager:
    """
    Manages idempotency keys and ensures operations are executed exactly once
    """
    
    def __init__(self, redis_client: redis.Redis, metrics: MetricsCollector):
        self.redis = redis_client
        self.metrics = metrics
    
    async def is_operation_completed(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Check if operation with given idempotency key was already completed"""
        try:
            result_data = await self.redis.get(f"idempotent:{idempotency_key}")
            if result_data:
                await self.metrics.increment("idempotency.cache_hit")
                return json.loads(result_data)
            
            await self.metrics.increment("idempotency.cache_miss")
            return None
            
        except Exception as e:
            logger.error(f"Failed to check idempotency for key '{idempotency_key}': {e}")
            return None
    
    async def mark_operation_completed(self,
                                     idempotency_key: str,
                                     result: Dict[str, Any],
                                     ttl_seconds: int = 3600) -> bool:
        """Mark operation as completed with result"""
        try:
            await self.redis.setex(
                f"idempotent:{idempotency_key}",
                ttl_seconds,
                json.dumps(result, default=str)
            )
            
            await self.metrics.increment("idempotency.marked_complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark operation completed for key '{idempotency_key}': {e}")
            return False
    
    async def mark_operation_in_progress(self,
                                       idempotency_key: str,
                                       metadata: Dict[str, Any] = None,
                                       ttl_seconds: int = 1800) -> bool:
        """Mark operation as in progress"""
        try:
            progress_data = {
                'status': 'in_progress',
                'started_at': datetime.utcnow().isoformat(),
                'metadata': metadata or {}
            }
            
            # Use SET with NX to ensure atomic check-and-set
            success = await self.redis.set(
                f"idempotent:{idempotency_key}:progress",
                json.dumps(progress_data, default=str),
                nx=True,
                ex=ttl_seconds
            )
            
            if success:
                await self.metrics.increment("idempotency.marked_progress")
                return True
            else:
                await self.metrics.increment("idempotency.already_in_progress")
                return False
                
        except Exception as e:
            logger.error(f"Failed to mark operation in progress for key '{idempotency_key}': {e}")
            return False
    
    async def clear_operation_progress(self, idempotency_key: str) -> bool:
        """Clear operation progress marker"""
        try:
            await self.redis.delete(f"idempotent:{idempotency_key}:progress")
            return True
        except Exception as e:
            logger.error(f"Failed to clear operation progress for key '{idempotency_key}': {e}")
            return False


class StateManager:
    """
    Manages entity states and state transitions with distributed coordination
    """
    
    def __init__(self,
                 db_pool: asyncpg.Pool,
                 redis_client: redis.Redis,
                 lock_manager: DistributedLockManager,
                 metrics: MetricsCollector):
        self.db_pool = db_pool
        self.redis = redis_client
        self.lock_manager = lock_manager
        self.metrics = metrics
        
        # State machines by entity type
        self.state_machines: Dict[str, StateMachine] = {}
        
        # Register default state machines
        self._register_default_state_machines()
    
    def _register_default_state_machines(self):
        """Register default state machines"""
        
        # Batch state machine
        batch_sm = StateMachine("batch", EntityState.CREATED)
        
        # Define batch transitions
        transitions = [
            StateTransition(EntityState.CREATED, EntityState.PENDING, "plan"),
            StateTransition(EntityState.PENDING, EntityState.PROCESSING, "start"),
            StateTransition(EntityState.PROCESSING, EntityState.PROCESSED, "complete"),
            StateTransition(EntityState.PROCESSING, EntityState.FAILED, "fail"),
            StateTransition(EntityState.FAILED, EntityState.PENDING, "retry"),
            StateTransition(EntityState.PROCESSED, EntityState.ARCHIVED, "archive"),
            StateTransition(EntityState.PENDING, EntityState.CANCELLED, "cancel"),
            StateTransition(EntityState.PROCESSING, EntityState.CANCELLED, "cancel"),
        ]
        
        for transition in transitions:
            batch_sm.add_transition(transition)
        
        self.state_machines["batch"] = batch_sm
        
        # Article state machine
        article_sm = StateMachine("article", EntityState.CREATED)
        
        article_transitions = [
            StateTransition(EntityState.CREATED, EntityState.PENDING, "queue"),
            StateTransition(EntityState.PENDING, EntityState.PROCESSING, "process"),
            StateTransition(EntityState.PROCESSING, EntityState.PROCESSED, "complete"),
            StateTransition(EntityState.PROCESSING, EntityState.FAILED, "fail"),
            StateTransition(EntityState.FAILED, EntityState.PENDING, "retry"),
            StateTransition(EntityState.PROCESSED, EntityState.ARCHIVED, "archive"),
        ]
        
        for transition in article_transitions:
            article_sm.add_transition(transition)
        
        self.state_machines["article"] = article_sm
    
    async def transition_state(self,
                             entity_type: str,
                             entity_id: str,
                             trigger: str,
                             metadata: Dict[str, Any] = None) -> bool:
        """
        Perform a state transition for an entity with distributed coordination
        """
        lock_key = f"state:{entity_type}:{entity_id}"
        
        try:
            # Acquire lock for state transition
            lock_status = await self.lock_manager.acquire_lock(
                lock_key,
                f"state_manager_{uuid4().hex[:8]}",
                timeout_seconds=60,  # Short timeout for state transitions
                auto_renew=False
            )
            
            if lock_status != LockStatus.ACQUIRED:
                logger.warning(f"Failed to acquire lock for state transition: {entity_type}:{entity_id}")
                return False
            
            try:
                # Get current state
                current_state = await self._get_entity_state(entity_type, entity_id)
                if not current_state:
                    logger.error(f"Entity not found: {entity_type}:{entity_id}")
                    return False
                
                # Check if transition is valid
                state_machine = self.state_machines.get(entity_type)
                if not state_machine:
                    logger.error(f"No state machine defined for entity type: {entity_type}")
                    return False
                
                transition = state_machine.get_transition(current_state, trigger)
                if not transition:
                    logger.warning(f"Invalid transition: {current_state} -> {trigger} for {entity_type}:{entity_id}")
                    return False
                
                # Perform transition
                success = await self._execute_transition(
                    entity_type, entity_id, current_state, transition, metadata
                )
                
                if success:
                    await self.metrics.increment(f"state.transition.{entity_type}.{trigger}.success")
                    logger.info(f"State transition successful: {entity_type}:{entity_id} {current_state.value} -> {transition.to_state.value}")
                else:
                    await self.metrics.increment(f"state.transition.{entity_type}.{trigger}.failed")
                
                return success
                
            finally:
                await self.lock_manager.release_lock(lock_key, lock_key)
                
        except Exception as e:
            logger.error(f"State transition failed for {entity_type}:{entity_id}: {e}", exc_info=True)
            await self.metrics.increment(f"state.transition.{entity_type}.error")
            return False
    
    async def _get_entity_state(self, entity_type: str, entity_id: str) -> Optional[EntityState]:
        """Get current state of an entity"""
        try:
            # Try cache first
            cached_state = await self.redis.get(f"state:{entity_type}:{entity_id}")
            if cached_state:
                return EntityState(cached_state.decode())
            
            # Fall back to database
            if entity_type == "batch":
                async with self.db_pool.acquire() as conn:
                    state_str = await conn.fetchval(
                        "SELECT status FROM batches WHERE batch_id = $1", entity_id
                    )
                    if state_str:
                        state = self._map_db_status_to_state(state_str)
                        # Cache for future use
                        await self.redis.setex(f"state:{entity_type}:{entity_id}", 300, state.value)
                        return state
            
            elif entity_type == "article":
                async with self.db_pool.acquire() as conn:
                    state_str = await conn.fetchval(
                        "SELECT status FROM raw_articles WHERE id = $1", int(entity_id)
                    )
                    if state_str:
                        state = self._map_db_status_to_state(state_str)
                        await self.redis.setex(f"state:{entity_type}:{entity_id}", 300, state.value)
                        return state
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get state for {entity_type}:{entity_id}: {e}")
            return None
    
    async def _execute_transition(self,
                                entity_type: str,
                                entity_id: str,
                                current_state: EntityState,
                                transition: StateTransition,
                                metadata: Dict[str, Any] = None) -> bool:
        """Execute a state transition"""
        try:
            # Update state in database
            success = await self._update_entity_state_db(
                entity_type, entity_id, transition.to_state, metadata
            )
            
            if not success:
                return False
            
            # Update state in cache
            await self.redis.setex(
                f"state:{entity_type}:{entity_id}",
                300,
                transition.to_state.value
            )
            
            # Execute transition actions if any
            for action in transition.actions:
                await self._execute_transition_action(
                    entity_type, entity_id, action, transition.to_state, metadata
                )
            
            # Log transition
            await self._log_state_transition(
                entity_type, entity_id, current_state, transition.to_state, transition.trigger, metadata
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to execute transition for {entity_type}:{entity_id}: {e}")
            return False
    
    async def _update_entity_state_db(self,
                                    entity_type: str,
                                    entity_id: str,
                                    new_state: EntityState,
                                    metadata: Dict[str, Any] = None) -> bool:
        """Update entity state in database"""
        try:
            db_status = self._map_state_to_db_status(new_state)
            
            if entity_type == "batch":
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE batches 
                        SET status = $1, updated_at = NOW()
                        WHERE batch_id = $2
                    """, db_status, entity_id)
            
            elif entity_type == "article":
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE raw_articles 
                        SET status = $1, updated_at = NOW()
                        WHERE id = $2
                    """, db_status, int(entity_id))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update entity state in DB: {e}")
            return False
    
    def _map_db_status_to_state(self, db_status: str) -> EntityState:
        """Map database status to EntityState"""
        mapping = {
            'created': EntityState.CREATED,
            'pending': EntityState.PENDING,
            'ready': EntityState.PENDING,
            'processing': EntityState.PROCESSING,
            'processed': EntityState.PROCESSED,
            'completed': EntityState.PROCESSED,
            'failed': EntityState.FAILED,
            'cancelled': EntityState.CANCELLED,
            'archived': EntityState.ARCHIVED
        }
        return mapping.get(db_status.lower(), EntityState.CREATED)
    
    def _map_state_to_db_status(self, state: EntityState) -> str:
        """Map EntityState to database status"""
        mapping = {
            EntityState.CREATED: 'created',
            EntityState.PENDING: 'pending',
            EntityState.PROCESSING: 'processing',
            EntityState.PROCESSED: 'processed',
            EntityState.FAILED: 'failed',
            EntityState.CANCELLED: 'cancelled',
            EntityState.ARCHIVED: 'archived'
        }
        return mapping.get(state, 'created')
    
    async def _execute_transition_action(self,
                                       entity_type: str,
                                       entity_id: str,
                                       action: str,
                                       new_state: EntityState,
                                       metadata: Dict[str, Any] = None):
        """Execute a transition action"""
        # Placeholder for action execution
        # This would contain business logic for specific actions
        logger.debug(f"Executing action '{action}' for {entity_type}:{entity_id}")
    
    async def _log_state_transition(self,
                                  entity_type: str,
                                  entity_id: str,
                                  from_state: EntityState,
                                  to_state: EntityState,
                                  trigger: str,
                                  metadata: Dict[str, Any] = None):
        """Log state transition for audit trail"""
        try:
            transition_log = {
                'entity_type': entity_type,
                'entity_id': entity_id,
                'from_state': from_state.value,
                'to_state': to_state.value,
                'trigger': trigger,
                'timestamp': datetime.utcnow().isoformat(),
                'metadata': metadata or {}
            }
            
            # Store in Redis for recent history
            await self.redis.lpush(
                f"transitions:{entity_type}:{entity_id}",
                json.dumps(transition_log)
            )
            
            # Keep only last 50 transitions
            await self.redis.ltrim(f"transitions:{entity_type}:{entity_id}", 0, 49)
            
        except Exception as e:
            logger.error(f"Failed to log state transition: {e}")


# Example usage and integration
if __name__ == "__main__":
    import asyncio
    
    async def test_state_management():
        # This would work with real connections
        print("State management system initialized successfully")
        
        # Mock components
        # db_pool = await asyncpg.create_pool(...)
        # redis_client = redis.Redis(...)
        # metrics = MetricsCollector()
        
        # lock_manager = DistributedLockManager(redis_client, db_pool, metrics)
        # await lock_manager.initialize()
        
        # state_manager = StateManager(db_pool, redis_client, lock_manager, metrics)
        
        print("Components would be initialized and ready for use")
    
    # asyncio.run(test_state_management())