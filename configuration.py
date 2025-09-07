"""
Production-grade Configuration Management System
Centralized, versioned configuration with hot reload, validation, and A/B testing capabilities.
"""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable, Type
from pathlib import Path
import hashlib
import weakref

import asyncpg
import redis.asyncio as redis
import yaml
from pydantic import BaseModel, Field, validator
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from monitoring import MetricsCollector

logger = logging.getLogger(__name__)


class ConfigSourceType(Enum):
    """Configuration source types"""
    FILE = "file"
    DATABASE = "database" 
    REDIS = "redis"
    ENVIRONMENT = "environment"


class ConfigFormat(Enum):
    """Configuration file formats"""
    JSON = "json"
    YAML = "yaml"
    TOML = "toml"


@dataclass
class ConfigVersion:
    """Configuration version tracking"""
    version: str
    created_at: datetime
    created_by: str
    description: str
    checksum: str
    source: ConfigSourceType
    rollback_version: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConfigValidationRule:
    """Configuration validation rule"""
    key_path: str
    rule_type: str  # required, type, range, enum, regex, custom
    rule_value: Any
    error_message: str
    severity: str = "error"  # error, warning, info


class BaseConfigSchema(BaseModel):
    """Base configuration schema with common validation"""
    
    class Config:
        extra = "allow"  # Allow additional fields
        validate_assignment = True
        
    def validate_custom_rules(self, rules: List[ConfigValidationRule]) -> List[str]:
        """Validate against custom rules"""
        errors = []
        
        for rule in rules:
            try:
                value = self._get_nested_value(rule.key_path)
                
                if rule.rule_type == "required" and value is None:
                    errors.append(f"{rule.key_path}: {rule.error_message}")
                elif rule.rule_type == "type" and value is not None:
                    expected_type = rule.rule_value
                    if not isinstance(value, expected_type):
                        errors.append(f"{rule.key_path}: Expected {expected_type.__name__}, got {type(value).__name__}")
                elif rule.rule_type == "range" and value is not None:
                    min_val, max_val = rule.rule_value
                    if not (min_val <= value <= max_val):
                        errors.append(f"{rule.key_path}: Value {value} not in range [{min_val}, {max_val}]")
                elif rule.rule_type == "enum" and value is not None:
                    if value not in rule.rule_value:
                        errors.append(f"{rule.key_path}: Value '{value}' not in allowed values {rule.rule_value}")
                        
            except Exception as e:
                errors.append(f"{rule.key_path}: Validation error - {e}")
        
        return errors
    
    def _get_nested_value(self, key_path: str) -> Any:
        """Get nested value by dot notation path"""
        keys = key_path.split('.')
        value = self.dict()
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return value


class PipelineConfig(BaseConfigSchema):
    """Pipeline-specific configuration schema"""
    
    # Batch processing
    batch_size_default: int = Field(200, ge=50, le=500)
    batch_size_min: int = Field(100, ge=10, le=200)
    batch_size_max: int = Field(300, ge=200, le=1000)
    batch_timeout_seconds: int = Field(300, ge=60, le=1800)
    
    # Processing stages
    stage_timeouts: Dict[str, int] = Field(default_factory=lambda: {
        "validation": 30,
        "deduplication": 60, 
        "normalization": 45,
        "text_cleaning": 90,
        "indexing": 120,
        "chunking": 60,
        "search_indexing": 30,
        "diagnostics": 15
    })
    
    # Quality thresholds
    min_word_count: int = Field(100, ge=10, le=1000)
    min_quality_score: float = Field(0.3, ge=0.0, le=1.0)
    max_duplicate_similarity: float = Field(0.85, ge=0.5, le=1.0)
    
    # Text processing
    chunking_target_size: int = Field(500, ge=100, le=2000)
    chunking_overlap: int = Field(50, ge=0, le=200)
    chunking_min_size: int = Field(100, ge=50, le=300)
    
    # Rate limiting
    domain_request_limit: int = Field(10, ge=1, le=100)
    domain_request_window: int = Field(60, ge=10, le=300)
    
    @validator('stage_timeouts')
    def validate_stage_timeouts(cls, v):
        required_stages = ["validation", "deduplication", "normalization", "text_cleaning", 
                         "indexing", "chunking", "search_indexing", "diagnostics"]
        
        for stage in required_stages:
            if stage not in v:
                raise ValueError(f"Missing timeout for stage: {stage}")
            if v[stage] <= 0:
                raise ValueError(f"Timeout for {stage} must be positive")
        
        return v


class DatabaseConfig(BaseConfigSchema):
    """Database configuration schema"""
    
    # Connection settings
    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    
    # Pool settings
    pool_min_size: int = Field(5, ge=1, le=20)
    pool_max_size: int = Field(20, ge=5, le=100)
    pool_timeout: int = Field(30, ge=5, le=120)
    command_timeout: int = Field(30, ge=5, le=300)
    
    # Performance settings
    statement_cache_size: int = Field(100, ge=0, le=1000)
    prepared_statement_cache: bool = Field(True)
    
    # SSL settings
    ssl_mode: str = Field("require", regex="^(disable|allow|prefer|require|verify-ca|verify-full)$")
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    
    def get_connection_url(self) -> str:
        """Generate PostgreSQL connection URL"""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}?sslmode={self.ssl_mode}"


class RedisConfig(BaseConfigSchema):
    """Redis configuration schema"""
    
    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)
    database: int = Field(0, ge=0, le=15)
    password: Optional[str] = None
    
    # Pool settings
    max_connections: int = Field(50, ge=1, le=500)
    socket_timeout: int = Field(30, ge=1, le=120)
    socket_connect_timeout: int = Field(10, ge=1, le=60)
    
    # Cluster settings
    cluster_enabled: bool = Field(False)
    cluster_nodes: List[str] = Field(default_factory=list)
    
    def get_connection_url(self) -> str:
        """Generate Redis connection URL"""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.database}"


class MonitoringConfig(BaseConfigSchema):
    """Monitoring and alerting configuration"""
    
    # Metrics collection
    metrics_enabled: bool = Field(True)
    metrics_flush_interval: int = Field(30, ge=5, le=300)
    metrics_buffer_size: int = Field(1000, ge=100, le=10000)
    
    # Alerting thresholds
    error_rate_warning: float = Field(0.05, ge=0.0, le=1.0)
    error_rate_critical: float = Field(0.10, ge=0.0, le=1.0)
    latency_warning_ms: int = Field(5000, ge=100, le=60000)
    latency_critical_ms: int = Field(10000, ge=1000, le=120000)
    queue_depth_warning: int = Field(5000, ge=100, le=100000)
    queue_depth_critical: int = Field(10000, ge=1000, le=200000)
    
    # Notification settings
    notification_channels: List[str] = Field(default_factory=lambda: ["email", "slack"])
    alert_cooldown_minutes: int = Field(15, ge=1, le=1440)


class SystemConfig(BaseConfigSchema):
    """Complete system configuration"""
    
    # Environment
    environment: str = Field("production", regex="^(development|testing|staging|production)$")
    debug_mode: bool = Field(False)
    log_level: str = Field("INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    
    # Sub-configurations
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    database: DatabaseConfig = Field(...)
    redis: RedisConfig = Field(...)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    
    # Feature flags
    features: Dict[str, bool] = Field(default_factory=lambda: {
        "advanced_chunking": True,
        "adaptive_batch_sizing": True,
        "circuit_breakers": True,
        "a_b_testing": False,
        "experimental_optimizations": False
    })
    
    # Version info
    config_version: str = Field("1.0.0")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('features')
    def validate_features(cls, v):
        """Validate feature flag dependencies"""
        if v.get("experimental_optimizations", False) and not v.get("adaptive_batch_sizing", False):
            raise ValueError("experimental_optimizations requires adaptive_batch_sizing to be enabled")
        return v


class ConfigurationManager:
    """
    Advanced configuration management system with:
    - Multiple source support (file, database, Redis, environment)
    - Hot reload capabilities
    - Version tracking and rollback
    - A/B testing support
    - Validation and schema enforcement
    - Audit logging
    """
    
    def __init__(self,
                 metrics: Optional[MetricsCollector] = None,
                 redis_client: Optional[redis.Redis] = None,
                 db_pool: Optional[asyncpg.Pool] = None):
        self.metrics = metrics
        self.redis = redis_client
        self.db_pool = db_pool
        
        # Configuration storage
        self._config: Optional[SystemConfig] = None
        self._config_lock = asyncio.Lock()
        self._config_version: Optional[ConfigVersion] = None
        
        # Change notifications
        self._change_callbacks: List[Callable[[SystemConfig, SystemConfig], None]] = []
        
        # File watching
        self._file_observer: Optional[Observer] = None
        self._watched_files: Dict[str, float] = {}  # file_path -> last_modified
        
        # A/B testing
        self._ab_tests: Dict[str, Dict[str, Any]] = {}
        self._user_assignments: Dict[str, str] = {}  # user_id -> variant
        
        # Validation rules
        self._validation_rules: List[ConfigValidationRule] = []
        self._setup_default_validation_rules()
        
        # Caching
        self._cache_ttl = 300  # 5 minutes
        self._cached_config: Optional[Tuple[SystemConfig, float]] = None
        
        # Version history
        self._version_history: List[ConfigVersion] = []
        
    def _setup_default_validation_rules(self):
        """Setup default validation rules"""
        rules = [
            ConfigValidationRule(
                key_path="pipeline.batch_size_default",
                rule_type="range", 
                rule_value=(50, 500),
                error_message="Batch size must be between 50 and 500"
            ),
            ConfigValidationRule(
                key_path="database.pool_max_size",
                rule_type="range",
                rule_value=(5, 100),
                error_message="Database pool max size must be between 5 and 100"
            ),
            ConfigValidationRule(
                key_path="monitoring.error_rate_critical",
                rule_type="range",
                rule_value=(0.0, 1.0),
                error_message="Error rate must be between 0.0 and 1.0"
            )
        ]
        
        self._validation_rules.extend(rules)
    
    async def load_config_from_file(self, file_path: Union[str, Path]) -> bool:
        """
        Load configuration from file
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path)
        
        try:
            if not file_path.exists():
                logger.error(f"Configuration file not found: {file_path}")
                return False
            
            # Determine format from extension
            format_mapping = {
                '.json': ConfigFormat.JSON,
                '.yaml': ConfigFormat.YAML,
                '.yml': ConfigFormat.YAML,
                '.toml': ConfigFormat.TOML
            }
            
            config_format = format_mapping.get(file_path.suffix.lower())
            if not config_format:
                logger.error(f"Unsupported configuration format: {file_path.suffix}")
                return False
            
            # Read file content
            content = file_path.read_text(encoding='utf-8')
            checksum = hashlib.sha256(content.encode()).hexdigest()
            
            # Parse content based on format
            if config_format == ConfigFormat.JSON:
                config_data = json.loads(content)
            elif config_format in (ConfigFormat.YAML,):
                config_data = yaml.safe_load(content)
            else:
                # TOML support would need additional dependency
                raise ValueError(f"Format {config_format} not yet implemented")
            
            # Create configuration object
            new_config = SystemConfig(**config_data)
            
            # Validate configuration
            validation_errors = await self._validate_config(new_config)
            if validation_errors:
                logger.error(f"Configuration validation failed: {validation_errors}")
                return False
            
            # Create version record
            version = ConfigVersion(
                version=f"file_{int(time.time())}",
                created_at=datetime.utcnow(),
                created_by="file_system",
                description=f"Loaded from {file_path}",
                checksum=checksum,
                source=ConfigSourceType.FILE
            )
            
            # Update configuration
            await self._update_config(new_config, version)
            
            # Setup file watching
            if self._file_observer is None:
                await self._setup_file_watching()
            
            self._watched_files[str(file_path)] = file_path.stat().st_mtime
            
            logger.info(f"Configuration loaded successfully from {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load configuration from {file_path}: {e}", exc_info=True)
            return False
    
    async def load_config_from_database(self, config_name: str = "default") -> bool:
        """Load configuration from database"""
        if not self.db_pool:
            logger.error("Database pool not configured")
            return False
        
        try:
            async with self.db_pool.acquire() as conn:
                # Get latest configuration
                row = await conn.fetchrow("""
                    SELECT config_data, version, created_at, created_by, description, checksum
                    FROM system_configurations
                    WHERE config_name = $1 AND active = true
                    ORDER BY created_at DESC
                    LIMIT 1
                """, config_name)
                
                if not row:
                    logger.error(f"No active configuration found with name: {config_name}")
                    return False
                
                # Parse configuration
                config_data = json.loads(row['config_data']) if isinstance(row['config_data'], str) else row['config_data']
                new_config = SystemConfig(**config_data)
                
                # Create version record
                version = ConfigVersion(
                    version=row['version'],
                    created_at=row['created_at'],
                    created_by=row['created_by'],
                    description=row['description'],
                    checksum=row['checksum'],
                    source=ConfigSourceType.DATABASE
                )
                
                # Validate and update
                validation_errors = await self._validate_config(new_config)
                if validation_errors:
                    logger.error(f"Configuration validation failed: {validation_errors}")
                    return False
                
                await self._update_config(new_config, version)
                
                logger.info(f"Configuration loaded from database: {config_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to load configuration from database: {e}", exc_info=True)
            return False
    
    async def save_config_to_database(self, 
                                    config_name: str = "default",
                                    description: str = "Auto-saved configuration",
                                    created_by: str = "system") -> bool:
        """Save current configuration to database"""
        if not self.db_pool or not self._config:
            logger.error("Database pool not configured or no config loaded")
            return False
        
        try:
            config_data = self._config.dict()
            config_json = json.dumps(config_data, default=str, indent=2)
            checksum = hashlib.sha256(config_json.encode()).hexdigest()
            
            # Generate version
            version = f"db_{int(time.time())}"
            
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    # Deactivate previous versions
                    await conn.execute("""
                        UPDATE system_configurations 
                        SET active = false 
                        WHERE config_name = $1 AND active = true
                    """, config_name)
                    
                    # Insert new configuration
                    await conn.execute("""
                        INSERT INTO system_configurations (
                            config_name, config_data, version, created_by, 
                            description, checksum, active, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, true, NOW())
                    """, config_name, config_json, version, created_by, description, checksum)
                
                logger.info(f"Configuration saved to database: {config_name} (version: {version})")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save configuration to database: {e}", exc_info=True)
            return False
    
    async def _validate_config(self, config: SystemConfig) -> List[str]:
        """Validate configuration against rules"""
        errors = []
        
        try:
            # Pydantic validation (automatic)
            config.dict()  # This will trigger validation
            
            # Custom validation rules
            custom_errors = config.validate_custom_rules(self._validation_rules)
            errors.extend(custom_errors)
            
            # Cross-field validation
            if config.pipeline.batch_size_min >= config.pipeline.batch_size_max:
                errors.append("pipeline.batch_size_min must be less than batch_size_max")
            
            if config.pipeline.chunking_overlap >= config.pipeline.chunking_target_size:
                errors.append("pipeline.chunking_overlap must be less than chunking_target_size")
            
            # Database connection validation (basic)
            if config.database.pool_min_size > config.database.pool_max_size:
                errors.append("database.pool_min_size must not exceed pool_max_size")
            
        except Exception as e:
            errors.append(f"Configuration parsing error: {e}")
        
        return errors
    
    async def _update_config(self, new_config: SystemConfig, version: ConfigVersion):
        """Update configuration with proper locking and notifications"""
        async with self._config_lock:
            old_config = self._config
            
            # Update configuration
            self._config = new_config
            self._config_version = version
            
            # Update version history
            self._version_history.append(version)
            
            # Keep only last 50 versions in memory
            if len(self._version_history) > 50:
                self._version_history = self._version_history[-50:]
            
            # Invalidate cache
            self._cached_config = None
            
            # Store in Redis cache if available
            if self.redis:
                try:
                    config_dict = new_config.dict()
                    await self.redis.setex(
                        "system:config:current",
                        self._cache_ttl,
                        json.dumps(config_dict, default=str)
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache configuration in Redis: {e}")
            
            # Notify callbacks
            for callback in self._change_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(old_config, new_config)
                    else:
                        callback(old_config, new_config)
                except Exception as e:
                    logger.error(f"Configuration change callback failed: {e}", exc_info=True)
            
            # Record metrics
            if self.metrics:
                await self.metrics.increment("config.updated", tags={
                    "source": version.source.value,
                    "version": version.version
                })
            
            logger.info(f"Configuration updated to version {version.version}")
    
    def get_config(self, use_cache: bool = True) -> Optional[SystemConfig]:
        """
        Get current configuration
        
        Args:
            use_cache: Whether to use cached version
            
        Returns:
            Current system configuration
        """
        if use_cache and self._cached_config:
            config, cached_at = self._cached_config
            if time.time() - cached_at < self._cache_ttl:
                return config
        
        if self._config:
            # Update cache
            self._cached_config = (self._config, time.time())
            return self._config
        
        return None
    
    def get(self, key_path: str, default: Any = None, user_id: str = None) -> Any:
        """
        Get configuration value by key path with A/B testing support
        
        Args:
            key_path: Dot-notation path to configuration value
            default: Default value if key not found
            user_id: User ID for A/B testing
            
        Returns:
            Configuration value
        """
        config = self.get_config()
        if not config:
            return default
        
        # Check A/B test overrides first
        if user_id and key_path in self._ab_tests:
            variant = self._get_user_variant(user_id, key_path)
            ab_config = self._ab_tests[key_path].get("variants", {}).get(variant)
            if ab_config and "value" in ab_config:
                return ab_config["value"]
        
        # Get value from configuration
        try:
            keys = key_path.split('.')
            value = config.dict()
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            
            return value
            
        except Exception as e:
            logger.error(f"Error getting configuration value {key_path}: {e}")
            return default
    
    def register_change_callback(self, callback: Callable[[SystemConfig, SystemConfig], None]):
        """Register callback for configuration changes"""
        self._change_callbacks.append(callback)
    
    def remove_change_callback(self, callback: Callable):
        """Remove configuration change callback"""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)
    
    async def setup_ab_test(self,
                          key_path: str,
                          variants: Dict[str, Any],
                          traffic_split: Dict[str, float],
                          description: str = "") -> bool:
        """
        Setup A/B test for configuration value
        
        Args:
            key_path: Configuration key to test
            variants: Variant configurations {"variant_name": {"value": value}}
            traffic_split: Traffic allocation {"variant_name": percentage}
            description: Test description
            
        Returns:
            True if successful
        """
        try:
            # Validate traffic split
            if abs(sum(traffic_split.values()) - 1.0) > 0.001:
                raise ValueError("Traffic split must sum to 1.0")
            
            # Store A/B test configuration
            self._ab_tests[key_path] = {
                "variants": variants,
                "traffic_split": traffic_split,
                "description": description,
                "created_at": datetime.utcnow(),
                "active": True
            }
            
            logger.info(f"A/B test setup for {key_path}: {list(variants.keys())}")
            
            if self.metrics:
                await self.metrics.increment("config.ab_test_created", tags={"key_path": key_path})
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup A/B test for {key_path}: {e}")
            return False
    
    def _get_user_variant(self, user_id: str, key_path: str) -> str:
        """Determine user's variant for A/B test"""
        if key_path not in self._ab_tests:
            return "control"
        
        # Check if user already assigned
        assignment_key = f"{user_id}:{key_path}"
        if assignment_key in self._user_assignments:
            return self._user_assignments[assignment_key]
        
        # Assign user to variant based on hash
        ab_test = self._ab_tests[key_path]
        traffic_split = ab_test["traffic_split"]
        
        # Use hash for deterministic assignment
        user_hash = int(hashlib.md5(f"{user_id}:{key_path}".encode()).hexdigest()[:8], 16)
        bucket = (user_hash % 100) / 100.0  # 0.0 to 1.0
        
        cumulative = 0.0
        for variant, percentage in traffic_split.items():
            cumulative += percentage
            if bucket <= cumulative:
                self._user_assignments[assignment_key] = variant
                return variant
        
        # Fallback to first variant
        first_variant = list(traffic_split.keys())[0]
        self._user_assignments[assignment_key] = first_variant
        return first_variant
    
    async def rollback_to_version(self, version: str) -> bool:
        """Rollback configuration to specific version"""
        try:
            if not self.db_pool:
                logger.error("Database pool required for version rollback")
                return False
            
            async with self.db_pool.acquire() as conn:
                # Find the version
                row = await conn.fetchrow("""
                    SELECT config_data, created_by, description, checksum
                    FROM system_configurations
                    WHERE version = $1
                    LIMIT 1
                """, version)
                
                if not row:
                    logger.error(f"Version not found: {version}")
                    return False
                
                # Load the configuration
                config_data = json.loads(row['config_data']) if isinstance(row['config_data'], str) else row['config_data']
                rollback_config = SystemConfig(**config_data)
                
                # Create new version record for rollback
                rollback_version = ConfigVersion(
                    version=f"rollback_{int(time.time())}",
                    created_at=datetime.utcnow(),
                    created_by=f"rollback_by_{row['created_by']}",
                    description=f"Rollback to version {version}: {row['description']}",
                    checksum=row['checksum'],
                    source=ConfigSourceType.DATABASE,
                    rollback_version=version
                )
                
                # Validate and apply
                validation_errors = await self._validate_config(rollback_config)
                if validation_errors:
                    logger.error(f"Rollback configuration validation failed: {validation_errors}")
                    return False
                
                await self._update_config(rollback_config, rollback_version)
                
                # Save to database
                await self.save_config_to_database(
                    description=rollback_version.description,
                    created_by=rollback_version.created_by
                )
                
                logger.info(f"Successfully rolled back to version {version}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to rollback to version {version}: {e}", exc_info=True)
            return False
    
    async def _setup_file_watching(self):
        """Setup file system watching for configuration files"""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            
            class ConfigFileHandler(FileSystemEventHandler):
                def __init__(self, config_manager):
                    self.config_manager = config_manager
                
                def on_modified(self, event):
                    if not event.is_directory and event.src_path in self.config_manager._watched_files:
                        asyncio.create_task(self.config_manager._handle_file_change(event.src_path))
            
            self._file_observer = Observer()
            handler = ConfigFileHandler(self)
            
            # Watch directories containing configuration files
            watched_dirs = set()
            for file_path in self._watched_files:
                dir_path = Path(file_path).parent
                if str(dir_path) not in watched_dirs:
                    self._file_observer.schedule(handler, str(dir_path), recursive=False)
                    watched_dirs.add(str(dir_path))
            
            self._file_observer.start()
            logger.info("Configuration file watching enabled")
            
        except ImportError:
            logger.warning("watchdog not available - file watching disabled")
        except Exception as e:
            logger.error(f"Failed to setup file watching: {e}")
    
    async def _handle_file_change(self, file_path: str):
        """Handle configuration file change"""
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                return
            
            current_mtime = file_path_obj.stat().st_mtime
            last_mtime = self._watched_files.get(file_path, 0)
            
            if current_mtime > last_mtime:
                logger.info(f"Configuration file changed: {file_path}")
                
                # Reload configuration
                success = await self.load_config_from_file(file_path)
                
                if success:
                    self._watched_files[file_path] = current_mtime
                    if self.metrics:
                        await self.metrics.increment("config.file_reloaded", tags={"file_path": file_path})
                else:
                    logger.error(f"Failed to reload configuration from {file_path}")
                    if self.metrics:
                        await self.metrics.increment("config.file_reload_error", tags={"file_path": file_path})
                        
        except Exception as e:
            logger.error(f"Error handling file change {file_path}: {e}", exc_info=True)
    
    def get_status(self) -> Dict[str, Any]:
        """Get configuration manager status"""
        return {
            "config_loaded": self._config is not None,
            "current_version": self._config_version.version if self._config_version else None,
            "version_history_count": len(self._version_history),
            "watched_files_count": len(self._watched_files),
            "active_ab_tests": list(self._ab_tests.keys()),
            "change_callbacks_count": len(self._change_callbacks),
            "file_watching_enabled": self._file_observer is not None,
            "cache_enabled": self._cached_config is not None
        }
    
    async def close(self):
        """Cleanup configuration manager"""
        if self._file_observer:
            self._file_observer.stop()
            self._file_observer.join()
        
        self._change_callbacks.clear()
        logger.info("Configuration manager closed")


# Example usage and configuration templates
DEFAULT_CONFIG_TEMPLATE = {
    "environment": "production",
    "debug_mode": False,
    "log_level": "INFO",
    
    "pipeline": {
        "batch_size_default": 200,
        "batch_size_min": 100,
        "batch_size_max": 300,
        "min_word_count": 100,
        "min_quality_score": 0.3,
        "chunking_target_size": 500,
        "chunking_overlap": 50
    },
    
    "database": {
        "host": "localhost",
        "port": 5432,
        "database": "rssnews_db",
        "username": "user",
        "password": "password",
        "pool_min_size": 5,
        "pool_max_size": 20,
        "ssl_mode": "prefer"
    },
    
    "redis": {
        "host": "localhost",
        "port": 6379,
        "database": 0,
        "max_connections": 50
    },
    
    "monitoring": {
        "metrics_enabled": True,
        "error_rate_warning": 0.05,
        "error_rate_critical": 0.10,
        "latency_warning_ms": 5000,
        "queue_depth_warning": 5000
    },
    
    "features": {
        "advanced_chunking": True,
        "adaptive_batch_sizing": True,
        "circuit_breakers": True,
        "a_b_testing": False
    }
}


if __name__ == "__main__":
    async def example_usage():
        """Example configuration management usage"""
        
        # Create configuration manager
        config_manager = ConfigurationManager()
        
        # Load from file
        # await config_manager.load_config_from_file("config.yaml")
        
        # Get configuration values
        batch_size = config_manager.get("pipeline.batch_size_default", 200)
        print(f"Batch size: {batch_size}")
        
        # Setup A/B test
        await config_manager.setup_ab_test(
            "pipeline.batch_size_default",
            variants={
                "control": {"value": 200},
                "large_batch": {"value": 300}
            },
            traffic_split={
                "control": 0.7,
                "large_batch": 0.3
            },
            description="Test larger batch sizes for performance"
        )
        
        # Get value with A/B testing
        user_batch_size = config_manager.get("pipeline.batch_size_default", 200, user_id="user123")
        print(f"User batch size: {user_batch_size}")
        
        print("Configuration management system ready")
    
    # asyncio.run(example_usage())