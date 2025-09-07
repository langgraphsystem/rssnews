# Configuration Guide

Comprehensive configuration guide for Stage 6 Hybrid Chunking system.

## Configuration Overview

Stage 6 uses Pydantic Settings for type-safe configuration management with support for:
- Environment variables
- Configuration files (.env)
- Environment-specific overrides
- Validation and type conversion

## Core Configuration

### Database Settings

```bash
# Required: Async PostgreSQL connection
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database

# Connection pool settings
DB_POOL_SIZE=10              # Number of connections in pool
DB_MAX_OVERFLOW=20           # Additional connections beyond pool size
DB_POOL_TIMEOUT=30           # Connection timeout in seconds
DB_ECHO_SQL=false           # Log SQL queries (debug only)
```

**Example configurations:**
```bash
# Local development
DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/stage6_dev

# Production with SSL
DATABASE_URL=postgresql+asyncpg://user:pass@db.company.com:5432/stage6?ssl=require

# Railway.app
DATABASE_URL=postgresql+asyncpg://postgres:password@host.proxy.rlwy.net:port/railway
```

### Redis Settings

```bash
# Required: Redis for Celery and caching
REDIS_URL=redis://host:port/db

# Connection settings
REDIS_MAX_CONNECTIONS=50     # Maximum connections to Redis
REDIS_SOCKET_TIMEOUT=30      # Socket timeout in seconds
```

**Example configurations:**
```bash
# Local development
REDIS_URL=redis://localhost:6379/0

# Production with auth
REDIS_URL=redis://:password@redis.company.com:6379/1

# Redis Cloud
REDIS_URL=redis://:password@redis-12345.cloud.redislabs.com:12345
```

### Gemini API Settings

```bash
# Required: Google Gemini API key
GEMINI_API_KEY=your-gemini-api-key-here

# API configuration
GEMINI_MODEL=gemini-2.5-flash          # Model to use
GEMINI_BASE_URL=https://generativelanguage.googleapis.com  # API endpoint
GEMINI_TIMEOUT_SECONDS=30              # Request timeout
GEMINI_MAX_RETRIES=3                   # Retry attempts
GEMINI_RETRY_DELAY_BASE=1              # Base retry delay (seconds)
GEMINI_RETRY_DELAY_MAX=60              # Maximum retry delay

# Circuit breaker settings
GEMINI_CIRCUIT_BREAKER_THRESHOLD=5     # Failures before opening
GEMINI_CIRCUIT_BREAKER_TIMEOUT=60      # Timeout before retry (seconds)

# Model parameters
GEMINI_TEMPERATURE=0.1                 # Response randomness (0.0-2.0)
GEMINI_TOP_P=0.95                      # Nucleus sampling
GEMINI_MAX_OUTPUT_TOKENS=1024          # Maximum response tokens
```

## Chunking Configuration

### Size Parameters

```bash
# Target chunk size (words)
CHUNKING_TARGET_WORDS=400      # Optimal chunk size
CHUNKING_MIN_WORDS=200         # Minimum acceptable size
CHUNKING_MAX_WORDS=600         # Maximum allowed size

# Overlap settings
CHUNKING_OVERLAP_WORDS=80      # Overlap between chunks (words)

# Character limits
CHUNKING_MIN_CHARS=800         # Minimum chunk size (characters)
CHUNKING_MAX_OFFSET=120        # Maximum LLM boundary adjustment
```

### Quality Routing

```bash
# LLM routing decision threshold
CHUNKING_CONFIDENCE_MIN=0.60   # Minimum confidence for LLM processing

# Quality factors (0.0-1.0 weights)
QUALITY_BOUNDARY_WEIGHT=0.3    # Boundary issue detection
QUALITY_SIZE_WEIGHT=0.3        # Size optimization
QUALITY_COMPLEXITY_WEIGHT=0.4  # Content complexity
```

**Tuning guidelines:**
- **News articles**: `TARGET_WORDS=300-400`, `OVERLAP=60-80`
- **Long-form content**: `TARGET_WORDS=500-600`, `OVERLAP=100-120` 
- **Technical documentation**: `TARGET_WORDS=400-500`, `OVERLAP=80-100`
- **Social media**: `TARGET_WORDS=200-300`, `OVERLAP=40-60`

## Rate Limiting Configuration

### LLM API Limits

```bash
# Rate limiting to protect API quotas
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=60           # Per-minute limit
RATE_LIMIT_MAX_LLM_CALLS_PER_DOMAIN=10       # Per-domain limit
RATE_LIMIT_MAX_LLM_CALLS_PER_BATCH=100       # Per-batch limit
RATE_LIMIT_MAX_LLM_PERCENTAGE_PER_BATCH=0.3  # Max 30% LLM usage
RATE_LIMIT_DAILY_COST_LIMIT_USD=10.0          # Daily budget limit
```

**Recommendations by scale:**
```bash
# Small scale (< 1000 articles/day)
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=30
RATE_LIMIT_DAILY_COST_LIMIT_USD=5.0

# Medium scale (1000-10000 articles/day)  
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=60
RATE_LIMIT_DAILY_COST_LIMIT_USD=25.0

# Large scale (10000+ articles/day)
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=120
RATE_LIMIT_DAILY_COST_LIMIT_USD=100.0
```

## Feature Flags

```bash
# Core features
LLM_ROUTING_ENABLED=true           # Enable intelligent LLM routing
LLM_CHUNK_REFINE_ENABLED=true      # Enable LLM chunk refinement

# Optional features  
BATCH_PROCESSING_ENABLED=true      # Enable batch processing
AUTO_DISCOVERY_ENABLED=false       # Auto-discover articles
METRICS_COLLECTION_ENABLED=true    # Collect performance metrics
```

## Observability Configuration

### Logging Settings

```bash
# Logging configuration
LOG_LEVEL=INFO                # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json              # json, console  
LOG_FILE_PATH=logs/stage6.log # Log file location (optional)

# Structured logging features
LOG_INCLUDE_TRACE_ID=true    # Include trace IDs in logs
LOG_FILTER_SENSITIVE=true    # Filter sensitive data
LOG_MAX_LINE_LENGTH=2000     # Maximum log line length
```

### Metrics Settings

```bash
# Prometheus metrics
METRICS_ENABLED=true          # Enable metrics collection
METRICS_PORT=8000            # Metrics HTTP port
METRICS_PATH=/metrics        # Metrics endpoint path
METRICS_NAMESPACE=stage6     # Metrics namespace

# Push gateway (optional)
METRICS_PUSH_GATEWAY_URL=http://localhost:9091  # Pushgateway URL
METRICS_PUSH_INTERVAL=60     # Push interval (seconds)
```

### Tracing Settings

```bash
# OpenTelemetry tracing
TRACING_ENABLED=true                              # Enable distributed tracing
TRACE_SAMPLE_RATE=0.1                            # Sample rate (0.0-1.0)
JAEGER_ENDPOINT=http://localhost:14268/api/traces # Jaeger collector URL

# Trace configuration
TRACE_DB_QUERIES=false       # Trace database queries (verbose)
TRACE_HTTP_REQUESTS=true     # Trace HTTP requests
```

### Health Check Settings

```bash
# Health monitoring
HEALTH_CHECK_ENABLED=true    # Enable health checks
HEALTH_CHECK_PORT=8001      # Health check HTTP port
HEALTH_CHECK_TIMEOUT=5      # Health check timeout (seconds)

# Component health checks
HEALTH_CHECK_DB=true        # Database connectivity
HEALTH_CHECK_REDIS=true     # Redis connectivity  
HEALTH_CHECK_LLM_API=true   # LLM API availability
```

## Environment-Specific Configuration

### Development Environment

```bash
# .env.development
ENVIRONMENT=development
DEBUG=true

# Relaxed limits for testing
CHUNKING_TARGET_WORDS=200
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=10
RATE_LIMIT_DAILY_COST_LIMIT_USD=1.0

# Verbose logging
LOG_LEVEL=DEBUG
LOG_FORMAT=console
DB_ECHO_SQL=true

# Development database
DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/stage6_dev
```

### Testing Environment

```bash
# .env.testing  
ENVIRONMENT=testing
DEBUG=false

# Test database (isolated)
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5432/stage6_test
REDIS_URL=redis://localhost:6379/15

# Minimal LLM usage
LLM_CHUNK_REFINE_ENABLED=false
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=5

# Fast processing
CHUNKING_TARGET_WORDS=100
CHUNKING_MIN_WORDS=50
CHUNKING_MAX_WORDS=200

# Quiet logging
LOG_LEVEL=WARNING
METRICS_ENABLED=false
TRACING_ENABLED=false
```

### Production Environment

```bash
# .env.production
ENVIRONMENT=production
DEBUG=false

# Production database with connection pooling
DATABASE_URL=postgresql+asyncpg://stage6:secure_password@db-prod:5432/stage6_prod
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40

# Production Redis
REDIS_URL=redis://:redis_password@redis-prod:6379/0
REDIS_MAX_CONNECTIONS=100

# Optimized chunking
CHUNKING_TARGET_WORDS=400
CHUNKING_OVERLAP_WORDS=80

# Production rate limits
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=120
RATE_LIMIT_DAILY_COST_LIMIT_USD=50.0

# Production logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE_PATH=/var/log/stage6/stage6.log

# Full observability
METRICS_ENABLED=true
TRACING_ENABLED=true
HEALTH_CHECK_ENABLED=true
```

## Advanced Configuration

### Custom Configuration Files

You can use YAML or TOML configuration files:

**config.yaml:**
```yaml
database:
  url: "postgresql+asyncpg://user:pass@host/db"
  pool_size: 10
  
chunking:
  target_words: 400
  min_words: 200
  max_words: 600
  overlap_words: 80
  
gemini:
  api_key: "${GEMINI_API_KEY}"
  model: "gemini-2.5-flash"
  temperature: 0.1
  
rate_limit:
  max_llm_calls_per_min: 60
  daily_cost_limit_usd: 10.0
```

Load with:
```bash
stage6 --config config.yaml process-articles --article-id 123
```

### Environment Variable Precedence

Configuration is loaded in this order (later values override earlier):
1. Default values in Settings class
2. Configuration file (if specified)
3. `.env` file in current directory
4. Environment variables
5. Command-line arguments

### Validation and Type Safety

Stage 6 validates all configuration at startup:

```python
from src.config.settings import Settings

try:
    settings = Settings()
    print("✅ Configuration valid")
except ValueError as e:
    print(f"❌ Configuration error: {e}")
```

Common validation errors:
- Invalid database URL format
- Missing required API keys
- Out-of-range numeric values
- Invalid enum values

### Dynamic Configuration Updates

Some settings can be updated at runtime:

```bash
# Update rate limits
redis-cli SET stage6:config:rate_limit:max_calls_per_min 120

# Update log level
curl -X POST http://localhost:8001/config/log_level -d '{"level": "DEBUG"}'
```

## Configuration Examples

### High-Performance Setup

```bash
# Optimized for throughput
CHUNKING_TARGET_WORDS=300           # Smaller chunks = faster processing
CHUNKING_OVERLAP_WORDS=50           # Less overlap = more chunks
DB_POOL_SIZE=25                     # More database connections
REDIS_MAX_CONNECTIONS=100           # More Redis connections  
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=150  # Higher API limit
```

### Cost-Optimized Setup

```bash
# Minimized LLM usage
CHUNKING_CONFIDENCE_MIN=0.8         # Higher threshold = fewer LLM calls
RATE_LIMIT_MAX_LLM_PERCENTAGE_PER_BATCH=0.15  # Max 15% LLM usage
RATE_LIMIT_DAILY_COST_LIMIT_USD=5.0 # Strict budget
LLM_ROUTING_ENABLED=true            # Smart routing to reduce costs
```

### High-Quality Setup

```bash
# Maximum quality focus
CHUNKING_CONFIDENCE_MIN=0.4         # Lower threshold = more LLM calls
CHUNKING_TARGET_WORDS=450           # Larger chunks for better context
CHUNKING_OVERLAP_WORDS=100          # More overlap for better coherence
RATE_LIMIT_MAX_LLM_PERCENTAGE_PER_BATCH=0.5  # Up to 50% LLM usage
GEMINI_TEMPERATURE=0.0              # More deterministic responses
```

## Configuration Best Practices

### Security
- **Never commit API keys** to version control
- **Use environment variables** for secrets
- **Rotate API keys** regularly
- **Use least-privilege** database accounts
- **Enable SSL/TLS** for database connections

### Performance
- **Tune connection pools** based on workload
- **Monitor resource usage** and adjust accordingly
- **Use appropriate chunking sizes** for your content type
- **Set realistic rate limits** to avoid API throttling
- **Enable caching** where appropriate

### Monitoring
- **Enable all observability features** in production
- **Set up alerting** on key metrics
- **Monitor API costs** and quotas
- **Track processing performance** trends
- **Log errors** with sufficient context

### Scalability
- **Plan for growth** in configuration limits
- **Use horizontal scaling** with multiple workers
- **Consider read replicas** for database scaling
- **Implement proper backpressure** handling
- **Monitor queue depths** and processing lag