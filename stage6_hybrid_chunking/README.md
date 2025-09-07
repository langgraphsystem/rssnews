# Stage 6: Hybrid Chunking with Gemini 2.5 Flash API

Production-grade article chunking system that combines deterministic base chunking with selective LLM refinement using Google's Gemini 2.5 Flash API.

## 🎯 Overview

Stage 6 implements a hybrid approach to article chunking:
- **Deterministic Base Chunking**: Fast, paragraph-aware chunking with sliding window fallback
- **Intelligent Quality Routing**: Multi-dimensional analysis to identify chunks needing refinement
- **Selective LLM Refinement**: Gemini 2.5 Flash API integration with circuit breaker protection
- **Production-Ready**: Comprehensive error handling, observability, and scalability features

## ✨ Key Features

### Chunking Engine
- 📄 **Paragraph-based chunking** with sentence boundary awareness
- 🔄 **Sliding window fallback** for long content
- 🎯 **Configurable target sizes** (200-600 words, 80-word overlap)
- 📊 **Quality-based routing** (boundary issues, complex formatting, size optimization)

### LLM Integration
- 🤖 **Gemini 2.5 Flash API** with comprehensive error handling
- ⚡ **Circuit breaker protection** and exponential backoff retry
- 🔄 **Rate limiting** (60 calls/min, 30% max batch usage, $10/day budget)
- 🎛️ **Selective processing** (only 20-30% of chunks use LLM)

### Production Features
- 📊 **Comprehensive observability** (Prometheus metrics, OpenTelemetry tracing, structured logging)
- 🏥 **Health monitoring** (database, LLM API, circuit breakers)
- ⚙️ **CLI and Celery integration** for scalable processing
- 🧪 **Full test coverage** (unit, integration, performance tests)

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone <repository-url>
cd stage6_hybrid_chunking

# Install with Poetry (recommended)
poetry install

# Or install with pip
pip install -r requirements.txt
```

### Configuration

1. **Copy environment template:**
```bash
cp .env.example .env
```

2. **Configure essential settings:**
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname

# Redis for Celery
REDIS_URL=redis://localhost:6379/0

# Gemini API
GEMINI_API_KEY=your-gemini-api-key-here
```

3. **Run database migrations:**
```bash
# Initialize Alembic (first time only)
alembic init alembic

# Run migrations
alembic upgrade head
```

### Basic Usage

#### CLI Processing
```bash
# Process specific articles
stage6 process-articles --article-id 123 --article-id 456

# Process articles from domain
stage6 process-articles --source-domain news.com --max-articles 100

# High priority processing
stage6 process-articles --source-domain breaking.news --priority urgent

# Check system status
stage6 status --watch

# Run health checks
stage6 health-check --detailed
```

#### Celery Worker
```bash
# Start worker
stage6 worker --queue stage6_processing --concurrency 4

# Or use celery directly
celery -A src.celery_app worker --loglevel=info --queues=stage6_processing
```

#### Python API
```python
from src.config.settings import Settings
from src.stage6.pipeline import Stage6Pipeline
from src.db.models import Article

# Initialize
settings = Settings()
db_session = await get_db_session()
pipeline = Stage6Pipeline(settings, db_session)

# Process articles
articles = [...]  # Your Article objects
result = await pipeline.process_articles_batch(articles)
print(f"Processed {result.articles_processed} articles")
```

## 📁 Project Structure

```
stage6_hybrid_chunking/
├── src/
│   ├── chunking/          # Core chunking logic
│   │   ├── base_chunker.py      # Deterministic chunking
│   │   └── quality_router.py    # LLM routing decisions
│   ├── llm/               # LLM integration
│   │   ├── gemini_client.py     # Gemini API client
│   │   └── prompts.py          # Prompt templates
│   ├── stage6/            # Pipeline orchestration
│   │   ├── pipeline.py         # Main processing pipeline
│   │   ├── processor.py        # Batch processor
│   │   └── coordinator.py      # Job coordinator
│   ├── db/                # Database models & migrations
│   ├── config/            # Configuration management
│   ├── utils/             # Utilities (metrics, logging, health)
│   ├── cli/               # Command-line interface
│   ├── tasks/             # Celery tasks
│   └── celery_app.py      # Celery configuration
├── tests/                 # Comprehensive test suite
├── docs/                  # Documentation
├── alembic/              # Database migrations
└── .env.example          # Environment template
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment (development/production/testing) | `development` |
| `DATABASE_URL` | Async PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection for Celery | Required |
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `CHUNKING_TARGET_WORDS` | Target chunk size in words | `400` |
| `RATE_LIMIT_MAX_LLM_CALLS_PER_MIN` | LLM API rate limit | `60` |
| `LLM_ROUTING_ENABLED` | Enable intelligent routing | `true` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `METRICS_ENABLED` | Enable Prometheus metrics | `true` |
| `TRACING_ENABLED` | Enable OpenTelemetry tracing | `true` |

### Chunking Configuration
```python
# Fine-tune chunking behavior
CHUNKING_TARGET_WORDS=400      # Target chunk size
CHUNKING_OVERLAP_WORDS=80      # Overlap between chunks
CHUNKING_MIN_WORDS=200         # Minimum chunk size
CHUNKING_MAX_WORDS=600         # Maximum chunk size
CHUNKING_MAX_OFFSET=120        # Max LLM boundary adjustment
```

### Rate Limiting
```python
# Protect against API abuse
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=60           # Per minute limit
RATE_LIMIT_MAX_LLM_CALLS_PER_DOMAIN=10       # Per domain limit
RATE_LIMIT_MAX_LLM_CALLS_PER_BATCH=100       # Per batch limit
RATE_LIMIT_MAX_LLM_PERCENTAGE_PER_BATCH=0.3  # Max 30% of batch
RATE_LIMIT_DAILY_COST_LIMIT_USD=10.0          # Budget protection
```

## 🏗️ Architecture

### Processing Flow

```mermaid
graph TB
    A[Articles] --> B[Base Chunker]
    B --> C[Raw Chunks]
    C --> D[Quality Router]
    D --> E{Needs LLM?}
    E -->|Yes| F[Gemini API]
    E -->|No| G[Keep Original]
    F --> H[LLM Refinement]
    H --> I[Apply Changes]
    G --> I
    I --> J[Final Chunks]
    J --> K[Database Storage]
```

### Component Architecture

```mermaid
graph TB
    CLI[CLI Commands] --> COORD[Batch Coordinator]
    COORD --> PROC[Chunk Processor]
    PROC --> PIPE[Pipeline]
    PIPE --> BASE[Base Chunker]
    PIPE --> ROUTER[Quality Router]
    PIPE --> LLM[Gemini Client]
    
    CELERY[Celery Workers] --> TASKS[Processing Tasks]
    TASKS --> PROC
    
    PIPE --> DB[(Database)]
    PIPE --> REDIS[(Redis)]
    
    METRICS[Metrics] --> PROM[Prometheus]
    TRACE[Tracing] --> JAEGER[Jaeger]
    HEALTH[Health Checks] --> MONITOR[Monitoring]
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m slow          # Performance tests

# Run tests with detailed output
pytest -v --tb=short

# Test specific modules
pytest tests/test_base_chunker.py
pytest tests/test_gemini_client.py
```

## 📊 Monitoring & Observability

### Metrics (Prometheus)
- **Processing metrics**: articles processed, chunks created, processing time
- **LLM metrics**: API calls, success rate, circuit breaker state
- **System metrics**: active jobs, queue size, database connections

### Tracing (OpenTelemetry)
- **Distributed tracing** across pipeline components
- **Automatic instrumentation** for SQLAlchemy and HTTPX
- **Custom spans** for chunking and LLM operations

### Health Checks
```bash
# Comprehensive health check
stage6 health-check --detailed

# Monitor specific components
stage6 status --watch --interval 3
```

### Logging
- **Structured JSON logging** in production
- **Trace context injection** for correlation
- **Component-specific loggers** with bound context
- **Sensitive data filtering** (API keys, credentials)

## 🔄 Deployment

### Docker Deployment
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["stage6", "worker", "--concurrency", "4"]
```

### Docker Compose
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: stage6
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    
  redis:
    image: redis:7-alpine
    
  worker:
    build: .
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:password@postgres:5432/stage6
      REDIS_URL: redis://redis:6379/0
      GEMINI_API_KEY: ${GEMINI_API_KEY}
    command: ["stage6", "worker", "--concurrency", "4"]
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: stage6-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: stage6-worker
  template:
    metadata:
      labels:
        app: stage6-worker
    spec:
      containers:
      - name: worker
        image: stage6:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: stage6-secrets
              key: database-url
        - name: GEMINI_API_KEY
          valueFrom:
            secretKeyRef:
              name: stage6-secrets
              key: gemini-api-key
```

## 🔧 Development

### Setup Development Environment
```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install --with dev

# Activate virtual environment
poetry shell

# Install pre-commit hooks
pre-commit install
```

### Code Quality
```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint code  
flake8 src/ tests/
mypy src/

# Run pre-commit checks
pre-commit run --all-files
```

### Adding New Features
1. Create feature branch: `git checkout -b feature/new-feature`
2. Implement changes with tests
3. Update documentation
4. Run full test suite: `pytest`
5. Submit pull request

## 🔍 Troubleshooting

### Common Issues

#### LLM API Errors
```bash
# Check circuit breaker status
stage6 health-check | grep llm_circuit_breaker

# Test API connectivity
stage6 process-articles --article-id 1 --dry-run
```

#### Database Connection Issues
```bash
# Test database connectivity
stage6 health-check | grep database

# Check connection pool
stage6 status | grep "Database Connections"
```

#### Performance Issues
```bash
# Monitor processing metrics
stage6 status --watch

# Check batch configuration
stage6 process-articles --batch-size 25 --source-domain slow.site
```

### Debug Mode
```bash
# Enable verbose logging
stage6 --verbose process-articles --article-id 123

# Enable tracing
TRACING_ENABLED=true stage6 process-articles --article-id 123
```

## 📈 Performance Guidelines

### Optimization Tips
- **Batch size**: 25-75 articles per batch depending on complexity
- **LLM usage**: Target 20-30% of chunks for cost efficiency  
- **Concurrency**: 4-8 workers per CPU core for I/O bound workloads
- **Database**: Use connection pooling and prepared statements
- **Monitoring**: Set up alerts for circuit breaker trips and high latency

### Scaling Recommendations
- **Horizontal scaling**: Add more Celery workers
- **Vertical scaling**: Increase worker concurrency
- **Database**: Consider read replicas for heavy read workloads
- **Caching**: Redis for frequently accessed data

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

For major changes, please open an issue first to discuss what you would like to change.

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: `/docs` directory
- **Examples**: `/examples` directory