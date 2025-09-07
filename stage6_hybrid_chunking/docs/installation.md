# Installation Guide

This guide covers the installation and setup of Stage 6 Hybrid Chunking system.

## Prerequisites

### System Requirements
- **Python**: 3.11 or higher
- **PostgreSQL**: 13 or higher (with async support)
- **Redis**: 6.0 or higher (for Celery)
- **Memory**: Minimum 4GB RAM (8GB+ recommended)
- **Storage**: 10GB+ available disk space

### API Requirements
- **Google Cloud Account** with Gemini API access
- **Gemini 2.5 Flash API Key** - Get from [Google AI Studio](https://aistudio.google.com/app/apikey)

## Installation Methods

### Option 1: Poetry (Recommended)

Poetry provides the best dependency management and virtual environment handling.

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Clone repository
git clone <repository-url>
cd stage6_hybrid_chunking

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### Option 2: pip + venv

Standard Python installation using pip and virtual environments.

```bash
# Clone repository
git clone <repository-url>
cd stage6_hybrid_chunking

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Option 3: Docker

Containerized deployment for production environments.

```bash
# Build Docker image
docker build -t stage6:latest .

# Run with docker-compose
docker-compose up -d
```

## Database Setup

### PostgreSQL Installation

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### macOS (Homebrew)
```bash
brew install postgresql
brew services start postgresql
```

#### Windows
Download and install from [PostgreSQL official site](https://www.postgresql.org/download/windows/)

### Database Configuration

1. **Create database and user:**
```sql
-- Connect as postgres user
sudo -u postgres psql

-- Create database
CREATE DATABASE stage6_chunking;

-- Create user with password
CREATE USER stage6_user WITH ENCRYPTED PASSWORD 'your_secure_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE stage6_chunking TO stage6_user;

-- Enable required extensions
\c stage6_chunking;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

2. **Configure async support:**
```sql
-- Install asyncpg-compatible settings
ALTER DATABASE stage6_chunking SET timezone TO 'UTC';
```

### Redis Installation

#### Ubuntu/Debian
```bash
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

#### macOS (Homebrew)
```bash
brew install redis
brew services start redis
```

#### Windows
Use [Redis for Windows](https://github.com/microsoftarchive/redis) or run via Docker.

## Configuration

### Environment Setup

1. **Copy environment template:**
```bash
cp .env.example .env
```

2. **Edit configuration file:**
```bash
# Required settings
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://stage6_user:your_secure_password@localhost:5432/stage6_chunking
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=your-gemini-api-key-here

# Optional tuning
CHUNKING_TARGET_WORDS=400
RATE_LIMIT_MAX_LLM_CALLS_PER_MIN=60
LOG_LEVEL=INFO
```

### Database Migrations

Initialize and run database migrations:

```bash
# Initialize Alembic (first time only)
alembic init alembic

# Edit alembic.ini to use your database URL
# Set sqlalchemy.url = postgresql+asyncpg://...

# Create initial migration
alembic revision --autogenerate -m "Initial migration"

# Run migrations
alembic upgrade head
```

### API Key Configuration

1. **Get Gemini API Key:**
   - Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
   - Create new API key
   - Copy the key value

2. **Secure storage options:**

   **Environment variable (recommended):**
   ```bash
   export GEMINI_API_KEY="your-key-here"
   ```

   **Environment file:**
   ```bash
   # .env
   GEMINI_API_KEY=your-key-here
   ```

   **Kubernetes secret:**
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: stage6-secrets
   data:
     gemini-api-key: <base64-encoded-key>
   ```

## Verification

### Test Installation

1. **Check CLI access:**
```bash
stage6 --version
```

2. **Test database connection:**
```bash
stage6 health-check --detailed
```

3. **Verify Gemini API:**
```bash
# Process a test article (if you have sample data)
stage6 process-articles --article-id 1 --dry-run
```

### Run Test Suite

```bash
# Install test dependencies
poetry install --with test

# Run basic tests
pytest tests/test_config.py

# Run health checks
pytest tests/test_health.py -v
```

## Performance Tuning

### Database Optimization

1. **PostgreSQL configuration (`postgresql.conf`):**
```ini
# Memory settings
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB

# Connection settings
max_connections = 100
shared_preload_libraries = 'pg_stat_statements'

# Async settings
wal_level = replica
max_wal_senders = 3
```

2. **Connection pooling:**
```bash
# .env
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
```

### Redis Optimization

1. **Redis configuration (`redis.conf`):**
```ini
# Memory management
maxmemory 512mb
maxmemory-policy allkeys-lru

# Persistence (optional for Celery)
save 900 1
save 300 10
save 60 10000
```

2. **Connection settings:**
```bash
# .env
REDIS_MAX_CONNECTIONS=50
REDIS_SOCKET_TIMEOUT=30
```

## Production Deployment

### Systemd Services

1. **Create worker service (`/etc/systemd/system/stage6-worker.service`):**
```ini
[Unit]
Description=Stage 6 Celery Worker
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=stage6
WorkingDirectory=/opt/stage6
Environment=PATH=/opt/stage6/venv/bin
ExecStart=/opt/stage6/venv/bin/stage6 worker --concurrency 4
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

2. **Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable stage6-worker
sudo systemctl start stage6-worker
```

### Monitoring Setup

1. **Prometheus metrics endpoint:**
```bash
# .env
METRICS_ENABLED=true
METRICS_PORT=8000
```

2. **Health check endpoint:**
```bash
# .env
HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_PORT=8001
```

3. **Log aggregation:**
```bash
# .env
LOG_FORMAT=json
LOG_LEVEL=INFO
```

## Troubleshooting

### Common Installation Issues

#### Poetry Installation Fails
```bash
# Alternative installation method
pip install poetry

# Or use pipx
pipx install poetry
```

#### Database Connection Errors
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection manually
psql -h localhost -U stage6_user -d stage6_chunking

# Check firewall
sudo ufw allow 5432/tcp
```

#### Redis Connection Issues
```bash
# Check Redis is running
sudo systemctl status redis-server

# Test Redis connection
redis-cli ping

# Check configuration
redis-cli config get "*"
```

#### Gemini API Issues
```bash
# Test API key
curl -H "Authorization: Bearer $GEMINI_API_KEY" \
     "https://generativelanguage.googleapis.com/v1beta/models"

# Check quota and billing in Google Cloud Console
```

### Getting Help

If you encounter issues:

1. **Check logs:**
```bash
# System logs
journalctl -u stage6-worker -f

# Application logs
tail -f logs/stage6.log
```

2. **Run diagnostics:**
```bash
stage6 health-check --detailed --timeout 30
```

3. **Debug mode:**
```bash
stage6 --verbose status
```

4. **Report issues:**
   - Check existing [GitHub Issues](https://github.com/your-org/stage6/issues)
   - Create new issue with logs and configuration (remove sensitive data)

## Next Steps

After successful installation:

1. **Read the [Configuration Guide](configuration.md)**
2. **Review [Usage Examples](usage.md)**
3. **Set up [Monitoring](monitoring.md)**
4. **Plan your [Deployment Strategy](deployment.md)**