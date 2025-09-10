"""
Production-grade Gemini 2.5 Flash API client with comprehensive error handling,
retry logic, circuit breaker, and rate limiting.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx
import structlog
from pydantic import BaseModel, ValidationError

try:
    from ..config.settings import Settings  # type: ignore
except Exception:
    from typing import Any as Settings  # type: ignore
try:
    from ..llm.prompts import ChunkRefinementPrompts, ValidationPrompts, select_optimal_prompt  # type: ignore
except Exception:
    # In test context, allow import failure; tests can patch methods directly
    class ChunkRefinementPrompts:  # type: ignore
        @staticmethod
        def build_refinement_prompt(*args, **kwargs):
            return "{}"
    def select_optimal_prompt(*args, **kwargs):
        return "base"
    class ValidationPrompts:  # type: ignore
        pass

logger = structlog.get_logger(__name__)


class APIErrorType(Enum):
    """API error type classification."""
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    NETWORK = "network"
    RESPONSE_PARSING = "response_parsing"
    QUOTA_EXCEEDED = "quota_exceeded"
    UNKNOWN = "unknown"


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class GeminiRequest:
    """Represents a Gemini API request."""
    request_id: str
    prompt: str
    chunk_metadata: Dict
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def estimated_tokens(self) -> int:
        """Estimate token count for this request."""
        return len(self.prompt) // 4  # Rough estimation


@dataclass 
class GeminiResponse:
    """Represents a Gemini API response."""
    request_id: str
    success: bool
    response_data: Optional[Dict] = None
    error_type: Optional[APIErrorType] = None
    error_message: Optional[str] = None
    tokens_used: int = 0
    latency_ms: float = 0
    retry_count: int = 0
    

class LLMRefinementResult(BaseModel):
    """Validated LLM refinement result."""
    action: str  # keep, merge_prev, merge_next, drop
    offset_adjust: int = 0  # -120 to +120
    semantic_type: str = "body"  # intro, body, list, quote, conclusion, code
    confidence: float = 0.5  # 0.0 to 1.0
    reason: str = ""
    
    class Config:
        extra = "forbid"  # Reject unknown fields


class CircuitBreaker:
    """Circuit breaker for API protection."""
    
    def __init__(self, threshold: int = 5, timeout: int = 60):
        self.threshold = threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
        
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if (self.last_failure_time and 
                datetime.utcnow() - self.last_failure_time >= timedelta(seconds=self.timeout)):
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        """Record successful execution."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        
    def record_failure(self):
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.threshold:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker OPEN", failure_count=self.failure_count)


class RateLimiter:
    """Rate limiter with sliding window."""
    
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: List[datetime] = []
        
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)
        
        # Remove old calls
        self.calls = [call_time for call_time in self.calls if call_time > cutoff]
        
        return len(self.calls) < self.max_calls
    
    def record_call(self):
        """Record a new API call."""
        self.calls.append(datetime.utcnow())
        
    def get_wait_time(self) -> float:
        """Get seconds to wait before next call is allowed."""
        if self.can_execute():
            return 0.0
            
        if not self.calls:
            return 0.0
            
        oldest_call = min(self.calls)
        wait_until = oldest_call + timedelta(seconds=self.window_seconds)
        wait_seconds = (wait_until - datetime.utcnow()).total_seconds()
        
        return max(0.0, wait_seconds)


class GeminiClient:
    """
    Production-grade Gemini 2.5 Flash API client with:
    - Exponential backoff retry logic
    - Circuit breaker protection
    - Rate limiting
    - Comprehensive error handling
    - Token usage tracking
    - Response validation
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        
        # HTTP client setup
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.gemini.timeout_seconds,
                write=10.0,
                pool=5.0
            ),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5
            )
        )
        
        # Protection mechanisms
        self.circuit_breaker = CircuitBreaker(
            threshold=settings.gemini.circuit_breaker_threshold,
            timeout=settings.gemini.circuit_breaker_timeout
        )
        
        self.rate_limiter = RateLimiter(
            max_calls=settings.rate_limit.max_llm_calls_per_min,
            window_seconds=60
        )
        
        # API configuration
        self.api_key = settings.gemini.api_key.get_secret_value()
        self.model = settings.gemini.model
        self.base_url = settings.gemini.base_url
        
        # Retry configuration
        self.max_retries = settings.gemini.max_retries
        self.retry_delay_base = settings.gemini.retry_delay_base
        self.retry_delay_max = settings.gemini.retry_delay_max
        
        # Tracking
        self.total_requests = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        
        logger.info("GeminiClient initialized", model=self.model)
    
    async def refine_chunk(self,
                          chunk_text: str,
                          chunk_metadata: Dict,
                          article_metadata: Dict,
                          context: Optional[Dict] = None) -> Optional[LLMRefinementResult]:
        """
        Refine a chunk using Gemini 2.5 Flash API.
        
        Args:
            chunk_text: Text content of the chunk
            chunk_metadata: Chunk metadata (index, word_count, etc.)
            article_metadata: Article metadata for context
            context: Additional context (prev/next chunks, etc.)
            
        Returns:
            LLMRefinementResult if successful, None if failed
        """
        request_id = f"gemini_{uuid4().hex[:8]}"
        
        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.warning("Circuit breaker OPEN, skipping request", request_id=request_id)
            return None
        
        # Check rate limiting
        if not self.rate_limiter.can_execute():
            wait_time = self.rate_limiter.get_wait_time()
            if wait_time > 30:  # Don't wait more than 30 seconds
                logger.warning("Rate limit exceeded, skipping request", 
                             request_id=request_id, wait_time=wait_time)
                return None
            
            logger.info("Rate limited, waiting", request_id=request_id, wait_time=wait_time)
            await asyncio.sleep(wait_time)
        
        # Build prompt
        quality_issues = chunk_metadata.get('quality_issues', [])
        api_context = {'retry_count': 0, 'token_limit_reached': False}
        
        template_type = select_optimal_prompt(chunk_metadata, quality_issues, api_context)
        
        prompt = ChunkRefinementPrompts.build_refinement_prompt(
            chunk_text=chunk_text,
            chunk_index=chunk_metadata.get('index', 0),
            word_count=chunk_metadata.get('word_count', len(chunk_text.split())),
            target_words=self.settings.chunking.target_words,
            max_offset=self.settings.chunking.max_offset,
            article_metadata=article_metadata,
            prev_context=context.get('prev_context', '') if context else '',
            next_context=context.get('next_context', '') if context else '',
            quality_issues=quality_issues,
            template_type=template_type
        )
        
        request = GeminiRequest(
            request_id=request_id,
            prompt=prompt,
            chunk_metadata=chunk_metadata
        )
        
        # Execute with retry logic
        response = await self._execute_request_with_retry(request)
        
        if response.success and response.response_data:
            try:
                # Validate and parse response
                result = self._parse_and_validate_response(
                    response.response_data, chunk_metadata
                )
                
                self.circuit_breaker.record_success()
                return result
                
            except Exception as e:
                logger.error("Response validation failed", 
                           request_id=request_id, error=str(e))
                self.circuit_breaker.record_failure()
                return None
        else:
            self.circuit_breaker.record_failure()
            return None
    
    async def _execute_request_with_retry(self, request: GeminiRequest) -> GeminiResponse:
        """Execute API request with exponential backoff retry."""
        
        for attempt in range(self.max_retries + 1):
            request.retry_count = attempt
            
            try:
                start_time = time.time()
                
                # Make API call
                response_data, tokens_used = await self._make_api_call(request)
                
                latency_ms = (time.time() - start_time) * 1000
                
                # Record metrics & cost
                self.rate_limiter.record_call()
                self.total_requests += 1
                self.total_tokens += tokens_used
                try:
                    # Approximate 80/20 input/output split
                    cost = (
                        (tokens_used * 0.8) * self.settings.rate_limit.cost_per_token_input
                        + (tokens_used * 0.2) * self.settings.rate_limit.cost_per_token_output
                    )
                    self.total_cost += float(cost)
                except Exception:
                    pass
                
                logger.info(
                    "API request successful",
                    request_id=request.request_id,
                    attempt=attempt + 1,
                    latency_ms=latency_ms,
                    tokens_used=tokens_used
                )
                
                return GeminiResponse(
                    request_id=request.request_id,
                    success=True,
                    response_data=response_data,
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                    retry_count=attempt
                )
                
            except Exception as e:
                error_type = self._classify_error(e)
                latency_ms = (time.time() - start_time) * 1000
                
                logger.warning(
                    "API request failed",
                    request_id=request.request_id,
                    attempt=attempt + 1,
                    error_type=error_type.value,
                    error=str(e),
                    latency_ms=latency_ms
                )
                
                # Check if we should retry
                if attempt >= self.max_retries or not self._should_retry(error_type):
                    return GeminiResponse(
                        request_id=request.request_id,
                        success=False,
                        error_type=error_type,
                        error_message=str(e),
                        latency_ms=latency_ms,
                        retry_count=attempt
                    )
                
                # Calculate retry delay with exponential backoff and jitter
                delay = min(
                    self.retry_delay_base * (2 ** attempt),
                    self.retry_delay_max
                )
                
                # Add jitter (±25%)
                import random
                jitter = delay * 0.25 * (2 * random.random() - 1)
                delay = max(0.1, delay + jitter)
                
                logger.info(f"Retrying in {delay:.2f}s", request_id=request.request_id)
                await asyncio.sleep(delay)
        
        # Should never reach here
        return GeminiResponse(
            request_id=request.request_id,
            success=False,
            error_type=APIErrorType.UNKNOWN,
            error_message="Max retries exceeded"
        )
    
    async def _make_api_call(self, request: GeminiRequest) -> Tuple[Dict, int]:
        """Make the actual API call to Gemini."""
        
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        
        # Gemini API expects API key in 'x-goog-api-key' header (or as query param), not Bearer auth
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request.prompt}]
                }
            ],
            "generationConfig": {
                "temperature": self.settings.gemini.temperature,
                "topP": self.settings.gemini.top_p,
                "maxOutputTokens": self.settings.gemini.max_output_tokens,
                "responseMimeType": "application/json"
            },
            "safetySettings": []  # Configure as needed
        }
        
        response = await self.client.post(url, headers=headers, json=payload)
        
        # Handle HTTP errors
        if response.status_code == 429:
            raise Exception(f"Rate limit exceeded: {response.text}")
        elif response.status_code == 401:
            raise Exception(f"Authentication failed: {response.text}")
        elif response.status_code >= 500:
            raise Exception(f"Server error {response.status_code}: {response.text}")
        elif response.status_code >= 400:
            raise Exception(f"Client error {response.status_code}: {response.text}")
        
        response.raise_for_status()
        
        # Parse response
        response_json = response.json()
        
        # Extract generated content
        candidates = response_json.get("candidates", [])
        if not candidates:
            raise Exception("No candidates in response")
        
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        
        if not parts:
            raise Exception("No content parts in response")
        
        generated_text = parts[0].get("text", "")
        
        if not generated_text:
            raise Exception("Empty generated text")
        
        # Parse JSON from generated text
        try:
            parsed_response = json.loads(generated_text)
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")
        
        # Estimate tokens used (rough approximation)
        tokens_used = len(request.prompt) // 4 + len(generated_text) // 4
        
        return parsed_response, tokens_used

    async def generate_text(self, prompt: str) -> str:
        """Generate plain text using current Gemini model. Returns empty string on failure."""
        try:
            url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
            headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": self.settings.gemini.temperature,
                    "topP": self.settings.gemini.top_p,
                    "maxOutputTokens": max(256, self.settings.gemini.max_output_tokens)
                },
                "safetySettings": []
            }
            r = await self.client.post(url, headers=headers, json=payload)
            if r.status_code != 200:
                return ""
            data = r.json()
            cands = data.get("candidates") or []
            if not cands:
                return ""
            parts = (cands[0].get("content") or {}).get("parts") or []
            if not parts:
                return ""
            return str(parts[0].get("text") or "")
        except Exception as e:
            logger.warning("generate_text_failed", err=str(e))
            return ""
    
    def _parse_and_validate_response(self, 
                                   response_data: Dict,
                                   chunk_metadata: Dict) -> LLMRefinementResult:
        """Parse and validate API response."""
        
        try:
            # Basic validation
            result = LLMRefinementResult(**response_data)
            
            # Additional validation
            valid_actions = {"keep", "merge_prev", "merge_next", "drop"}
            if result.action not in valid_actions:
                raise ValueError(f"Invalid action: {result.action}")
            
            if not (-120 <= result.offset_adjust <= 120):
                logger.warning(
                    "Offset adjust out of range, clamping",
                    original=result.offset_adjust
                )
                result.offset_adjust = max(-120, min(120, result.offset_adjust))
            
            valid_semantic_types = {"intro", "body", "list", "quote", "conclusion", "code"}
            if result.semantic_type not in valid_semantic_types:
                logger.warning(
                    "Invalid semantic type, defaulting to body",
                    original=result.semantic_type
                )
                result.semantic_type = "body"
            
            if not (0.0 <= result.confidence <= 1.0):
                logger.warning(
                    "Confidence out of range, clamping",
                    original=result.confidence
                )
                result.confidence = max(0.0, min(1.0, result.confidence))
            
            return result
            
        except ValidationError as e:
            logger.error("Response validation failed", errors=e.errors())
            raise
        except Exception as e:
            logger.error("Response parsing failed", error=str(e))
            raise
    
    def _classify_error(self, error: Exception) -> APIErrorType:
        """Classify error type for retry logic."""
        error_str = str(error).lower()
        
        if "rate limit" in error_str or "429" in error_str:
            return APIErrorType.RATE_LIMIT
        elif "authentication" in error_str or "401" in error_str:
            return APIErrorType.AUTHENTICATION
        elif "quota" in error_str or "exceeded" in error_str:
            return APIErrorType.QUOTA_EXCEEDED
        elif "timeout" in error_str:
            return APIErrorType.TIMEOUT
        elif "connection" in error_str or "network" in error_str:
            return APIErrorType.NETWORK
        elif "500" in error_str or "502" in error_str or "503" in error_str:
            return APIErrorType.SERVER_ERROR
        elif "400" in error_str or "invalid" in error_str:
            return APIErrorType.INVALID_REQUEST
        elif "json" in error_str or "parse" in error_str:
            return APIErrorType.RESPONSE_PARSING
        else:
            return APIErrorType.UNKNOWN
    
    def _should_retry(self, error_type: APIErrorType) -> bool:
        """Determine if error type should be retried."""
        retryable_errors = {
            APIErrorType.RATE_LIMIT,
            APIErrorType.SERVER_ERROR,
            APIErrorType.TIMEOUT,
            APIErrorType.NETWORK,
            APIErrorType.UNKNOWN
        }
        
        return error_type in retryable_errors
    
    async def health_check(self) -> bool:
        """Check if API is healthy."""
        try:
            # Simple test request
            test_request = GeminiRequest(
                request_id="health_check",
                prompt="Respond with JSON: {\"status\": \"healthy\"}",
                chunk_metadata={}
            )
            
            response = await self._execute_request_with_retry(test_request)
            return response.success
            
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            return False
    
    def get_stats(self) -> Dict:
        """Get client statistics."""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.total_cost,
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "circuit_breaker_failures": self.circuit_breaker.failure_count,
            "rate_limiter_calls_window": len(self.rate_limiter.calls)
        }
    
    async def close(self):
        """Clean up resources."""
        await self.client.aclose()
        logger.info("GeminiClient closed")

    # --------------- High level helpers ---------------
    async def refine_chunks_via_llm(self, chunks: List[Dict], meta: Dict) -> List[LLMRefinementResult]:
        """Refine a list of chunks, returning one LLMRefinementResult per chunk.

        On any failure, returns 'keep' actions for remaining chunks to preserve determinism.
        """
        results: List[LLMRefinementResult] = []
        for i, c in enumerate(chunks):
            try:
                cm = {
                    'chunk_index': c.get('chunk_index', i),
                    'char_start': c.get('char_start', 0),
                    'char_end': c.get('char_end', 0),
                    'semantic_type': c.get('semantic_type', 'body')
                }
                prompt_type = 'base'
                res = await self.send_refinement_request(c.get('text', ''), cm, prompt_type)
                if res is None:
                    results.append(LLMRefinementResult(action='keep', offset_adjust=0, semantic_type=cm['semantic_type'], confidence=0.0, reason='fallback'))
                else:
                    results.append(res)
            except Exception as e:
                logger.warning("refine_chunk_failed", idx=i, err=str(e))
                results.append(LLMRefinementResult(action='keep', offset_adjust=0, semantic_type=c.get('semantic_type','body'), confidence=0.0, reason='error'))
        return results

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a batch of texts using the configured embedding model.
        If API fails or key missing, returns empty list for each text.
        """
        if not self.settings.gemini.embedding_model:
            return [[] for _ in texts]
        model = (self.settings.gemini.embedding_model or '').strip()
        # Branch 1: Use google-generativeai client for gemini-embedding-001
        if model == 'gemini-embedding-001' or model.endswith('/gemini-embedding-001'):
            try:
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=self.api_key)
                api_model = model if model.startswith('models/') else f'models/{model}'
                out: List[List[float]] = []
                for t in texts:
                    try:
                        res = genai.embed_content(
                            model=api_model,
                            content=t[:2000],
                            task_type="RETRIEVAL_DOCUMENT"
                        )
                        vec = None
                        if isinstance(res, dict):
                            emb = res.get('embedding')
                            if isinstance(emb, dict):
                                vec = emb.get('values') or emb.get('value')
                            elif isinstance(emb, list):
                                vec = emb
                        if isinstance(vec, list):
                            out.append([float(x) for x in vec])
                        else:
                            out.append([])
                    except Exception as e:
                        logger.warning("embed_single_failed_genai", err=str(e))
                        out.append([])
                return out
            except Exception as e:
                logger.warning("embed_texts_genai_failed", err=str(e))
                # fall through to HTTP path

        # Branch 2: Direct Generative Language API (e.g., text-embedding-004)
        try:
            api_model = model if model.startswith('models/') else f'models/{model}'
            base = self.base_url.rstrip('/')
            url = f"{base}/v1beta/{api_model}:embedContent"
            headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
            out: List[List[float]] = []
            ac = self.client
            for t in texts:
                payload = {"content": {"parts": [{"text": t[:2000]}]}}
                r = await ac.post(url, headers=headers, json=payload)
                if r.status_code != 200:
                    out.append([])
                    continue
                data = r.json()
                vec = data.get('embedding', {}).get('values') or data.get('embedding', {}).get('value')
                if isinstance(vec, list):
                    out.append([float(x) for x in vec])
                else:
                    out.append([])
            return out
        except Exception as e:
            logger.warning("embed_texts_failed", err=str(e))
            return [[] for _ in texts]
