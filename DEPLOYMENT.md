# 🚀 RSS News System - Production Deployment Guide

## 📋 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- 4GB+ RAM
- PostgreSQL with pgvector support
- Redis server
- OpenAI API key (for GPT-5)
- Telegram Bot Token

### 2. Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required Configuration:**
```bash
# Essential settings
DB_PASSWORD=your_secure_password
OPENAI_API_KEY=sk-proj-your-api-key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# Initialize database schema
docker-compose exec rss-news python setup_production_db.py

# Check system health
docker-compose exec rss-news python ranking_api.py health
```

### 4. Service URLs

- **Main API**: http://localhost:8000
- **Redis**: localhost:6379
- **PostgreSQL**: localhost:5432
- **Ollama**: http://localhost:11434
- **Grafana** (optional): http://localhost:3000

## 🔧 Manual Setup (Alternative)

### 1. Install Dependencies

```bash
# Install latest libraries (2025 versions)
pip install -r requirements.txt
```

### 2. Database Setup

```bash
# Setup production database
python setup_production_db.py

# Verify installation
python ranking_api.py health
```

### 3. Start Services

```bash
# Terminal 1: Main API
python ranking_api.py

# Terminal 2: Service Manager
python services/service_manager.py start

# Terminal 3: Telegram Bot
python bot_service/advanced_bot.py

# Terminal 4: System Stats (optional)
python system_stats_reporter.py
```

## 📊 Library Versions (2025 Latest)

**Core ML/AI Libraries:**
- `numpy==2.3.3` (September 2025 release)
- `scikit-learn==1.7.2` (includes HDBSCAN)
- `datasketch==1.6.5` (MinHash deduplication)
- `hdbscan==0.8.38` (clustering)
- `umap-learn==0.5.8` (dimensionality reduction)

**Production Dependencies:**
- `openai==1.108.2` (GPT-5 support)
- `redis==5.2.0` (caching)
- `psycopg2-binary==2.9.10` (PostgreSQL)

## ⚙️ Configuration Management

### Scoring Weights (Environment Variables)
```bash
SCORING_SEMANTIC_WEIGHT=0.58    # Semantic similarity
SCORING_FTS_WEIGHT=0.32         # Full-text search
SCORING_FRESHNESS_WEIGHT=0.06   # Time decay
SCORING_SOURCE_WEIGHT=0.04      # Source authority
```

### Performance Tuning
```bash
SCORING_MAX_PER_DOMAIN=3        # Domain diversity
SEARCH_CACHE_TTL_SECONDS=900    # Cache duration
ENABLE_MMR_DIVERSIFICATION=true # Result diversity
```

## 🐳 Docker Services

### Core Services
- **rss-news**: Main application
- **postgres**: Database with pgvector
- **redis**: Caching & queues
- **ollama**: Local LLM

### Background Services
- **service-manager**: Processing pipeline
- **telegram-bot**: Bot interface

### Monitoring (Optional)
```bash
# Start with monitoring
docker-compose --profile monitoring up -d
```

## 🔍 Testing & Validation

### 1. System Health Check
```bash
python ranking_api.py health
```

### 2. Search Testing
```bash
# Test hybrid search
python ranking_api.py search --query "artificial intelligence" --explain

# Test RAG questions
python ranking_api.py ask --query "what is machine learning?"
```

### 3. Bot Testing
```bash
# Send test message to bot
/search artificial intelligence
/ask what is AI?
/trends
/quality
```

## 📈 Monitoring & Metrics

### Quality Metrics Tracked
- **nDCG@10**: Search relevance quality
- **Fresh@10**: Freshness of top results
- **Duplicates@10**: Duplicate detection rate
- **Response Time**: P95/P99 latency

### System Health Endpoints
- `/health` - Overall system status
- `/metrics` - Prometheus metrics
- `/quality` - Search quality report

## 🔒 Security Considerations

### Production Checklist
- ✅ Environment variables (no hardcoded secrets)
- ✅ Non-root Docker user
- ✅ Rate limiting enabled
- ✅ Input validation
- ✅ Error logging (no sensitive data)

### Database Security
- ✅ Strong passwords
- ✅ Connection encryption
- ✅ Regular backups
- ✅ Data retention policies

## 🚨 Troubleshooting

### Common Issues

**1. Database Connection Failed**
```bash
# Check PostgreSQL status
docker-compose logs postgres

# Verify connection string
echo $PG_DSN
```

**2. Ollama Model Not Found**
```bash
# Pull required model
docker-compose exec ollama ollama pull qwen2.5-coder:3b
```

**3. Search Returns Empty Results**
```bash
# Check embedding service
python ranking_api.py health

# Verify database has articles
python -c "from database.production_db_client import ProductionDBClient; print(ProductionDBClient().get_search_analytics())"
```

**4. Bot Not Responding**
```bash
# Check bot token
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"

# Check logs
docker-compose logs telegram-bot
```

## 📚 Advanced Configuration

### Custom Weights via Database
```python
from database.production_db_client import ProductionDBClient
db = ProductionDBClient()

# Update scoring weights
db.set_config_value('scoring.semantic_weight', 0.65, 'number')
db.set_config_value('scoring.fts_weight', 0.30, 'number')
```

### Performance Optimization
```bash
# Increase batch sizes for high-volume
export EMBEDDING_BATCH_SIZE=3000
export FTS_BATCH_SIZE=200000

# Enable GPU acceleration (if available)
pip install cuml-cu12
export CUDA_VISIBLE_DEVICES=0
```

## 🔄 Maintenance

### Regular Tasks
```bash
# Clean old search logs (60 days)
docker-compose exec postgres psql -U postgres -d rssnews -c "SELECT cleanup_old_search_logs();"

# Update domain scores
python -c "from database.production_db_client import ProductionDBClient; ProductionDBClient().cleanup_old_data()"

# Health monitoring
curl http://localhost:8000/health
```

### Updates & Upgrades
```bash
# Pull latest images
docker-compose pull

# Restart services
docker-compose down && docker-compose up -d

# Verify after update
python ranking_api.py health
```

---

## 🎯 Production Ready Features

✅ **Hybrid Ranking**: Semantic + FTS + Freshness + Authority
✅ **Deduplication**: MinHash-based content canonicalization
✅ **Explainability**: "Why this result?" transparency
✅ **Quality Metrics**: nDCG@10, Fresh@10, Duplicates@10
✅ **Advanced Bot**: Interactive search with explanations
✅ **Caching**: Redis-backed performance optimization
✅ **Monitoring**: Health checks & system metrics
✅ **Scalability**: Docker composition for horizontal scaling

**System is production-ready! 🚀**