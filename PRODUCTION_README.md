# Production RSS Processing System

## 🚀 Overview

A high-performance, production-ready RSS processing system capable of handling millions of articles per day with enterprise-grade reliability, monitoring, and scalability.

## 🏗️ Architecture

### Core Components

1. **8-Stage Pipeline Processor** (`pipeline_processor.py`)
   - Stage 0: Feed validation and filtering
   - Stage 1: Feed health monitoring and scoring  
   - Stage 2: Deduplication (hard & soft)
   - Stage 3: Normalization (dates, language, categories)
   - Stage 4: Text cleaning and boilerplate removal
   - Stage 5: Article indexing and quality scoring
   - Stage 6: Semantic chunking for search
   - Stage 7: Full-text search indexing
   - Stage 8: Comprehensive diagnostics and metrics

2. **Intelligent Batch Planner** (`batch_planner.py`)
   - Adaptive batch sizing (100-300 articles)
   - Priority-based processing
   - Domain fairness and load balancing
   - Automatic backpressure handling

3. **Distributed Task Queue** (`task_queue.py`)
   - Celery + Redis-based task execution
   - Priority queues with automatic routing
   - Exponential backoff retry logic
   - Circuit breaker protection

4. **Advanced Throttling System** (`throttling.py`)
   - Circuit breakers for service protection
   - Rate limiting (sliding window, token bucket, adaptive)
   - Intelligent backpressure management
   - System load monitoring and adjustment

5. **Connection Pool Manager** (`connection_manager.py`)
   - PostgreSQL connection pooling with health monitoring
   - Redis connection management
   - Automatic optimization and scaling
   - Performance metrics and diagnostics

6. **Configuration Management** (`configuration.py`)
   - Hot-reload configuration system
   - Version tracking and rollback
   - A/B testing support
   - Schema validation and audit logging

7. **Production Monitoring** (`monitoring.py`)
   - Prometheus-compatible metrics
   - Intelligent alerting with suppression
   - Real-time dashboards
   - Performance analytics and SLO tracking

## 📊 Key Performance Specifications

- **Throughput**: ≥10,000 articles/minute peak processing
- **Batch Size**: 200 articles (adaptive 100-300 range)
- **Parallelism**: Up to 50 concurrent workers
- **SLA**: 99.9% availability
- **Latency**: p99 < 5 seconds per batch
- **Error Handling**: Graceful degradation with backpressure
- **Storage**: Railway PostgreSQL with partitioning
- **Queue**: Redis-backed Celery with priority routing

## 🛠️ Installation & Setup

### Prerequisites

1. **Python 3.9+**
2. **PostgreSQL 13+** (Railway hosted)
3. **Redis 6+**
4. **RAM**: 4GB minimum, 8GB recommended
5. **CPU**: 4 cores minimum for production load

### Installation Steps

1. **Clone and Install Dependencies**
```bash
git clone <repository>
cd rssnews
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Database Setup**
```bash
# Apply schema (already configured for Railway)
python -c "
import asyncio
from connection_manager import ConnectionPoolManager, PoolConfiguration
from configuration import DatabaseConfig

async def setup_db():
    # Use your own connection settings or PG_DSN environment variable
    db_config = DatabaseConfig(
        host='YOUR_PG_HOST',
        port=5432,
        database='YOUR_DB_NAME',
        username='YOUR_DB_USER',
        password='YOUR_DB_PASSWORD'
    )
    
    manager = ConnectionPoolManager()
    await manager.add_database_pool('main', db_config.get_connection_url())
    print('Database connection successful')
    await manager.close_all()

asyncio.run(setup_db())
"
```

3. **Redis Setup**
```bash
# Start Redis server (or use hosted Redis)
redis-server
```

4. **Configuration**
```bash
# Create configuration file
cp config_example.json config.json
# Edit config.json with your settings
```

## 🚦 Production Deployment

### Running the Complete System

```bash
# Full system with all components
python main_production.py --config config.json --mode full --log-level INFO
```

### Distributed Deployment

#### Master Node (Scheduler + Monitor)
```bash
python main_production.py --mode scheduler --config config.json
```

#### Worker Nodes
```bash
# Start Celery workers
celery -A task_queue worker --loglevel=info --concurrency=10 --queues=batch_processing,emergency

# Start additional specialized workers
celery -A task_queue worker --loglevel=info --concurrency=5 --queues=feed_management,maintenance
```

#### Background Services
```bash
# Start Celery beat scheduler
celery -A task_queue beat --loglevel=info

# Start monitoring dashboard
python -m monitoring --port 8080
```

## 📈 Monitoring & Observability

### Key Metrics Dashboard

Access real-time metrics via:
```python
from main_production import ProductionRSSSystem
system = ProductionRSSSystem()
status = await system.get_system_status()
print(json.dumps(status, indent=2))
```

### Critical SLO Metrics

1. **Throughput**: `pipeline.batch.throughput` (articles/min)
2. **Latency**: `pipeline.batch.duration.p99` (seconds)
3. **Success Rate**: `pipeline.batch.success_rate` (%)
4. **Error Rate**: `pipeline.batch.error_rate` (%)
5. **Queue Depth**: `queue.pending_articles` (count)

### Alerting Thresholds

- **CRITICAL**: Error rate > 10%, Latency p99 > 10s, Queue depth > 10k
- **WARNING**: Error rate > 5%, Latency p99 > 5s, Queue depth > 5k
- **INFO**: High duplicate rate > 30%, Memory usage > 80%

## 🔧 Configuration Management

### Hot Reload Configuration
```bash
# Update configuration without restart
curl -X POST http://localhost:8080/config/reload
```

### A/B Testing
```python
# Setup A/B test for batch size
await config_manager.setup_ab_test(
    "pipeline.batch_size_default",
    variants={
        "control": {"value": 200},
        "large_batch": {"value": 300}
    },
    traffic_split={"control": 0.7, "large_batch": 0.3}
)
```

### Version Management
```bash
# Rollback to previous version
await config_manager.rollback_to_version("version_20240830_142000")
```

## 🚨 Emergency Procedures

### Create Emergency Batch
```bash
python -c "
import asyncio
from main_production import ProductionRSSSystem

async def emergency():
    system = ProductionRSSSystem()
    await system.initialize()
    batch_id = await system.create_emergency_batch(max_size=50)
    print(f'Emergency batch created: {batch_id}')

asyncio.run(emergency())
"
```

### System Health Check
```bash
python -c "
import asyncio
from connection_manager import ConnectionPoolManager

async def health_check():
    manager = ConnectionPoolManager()
    # ... health check logic
    print('System healthy')

asyncio.run(health_check())
"
```

## 🔍 Troubleshooting

### Common Issues

1. **High Memory Usage**
   - Reduce batch size: Set `pipeline.batch_size_default = 150`
   - Check connection pool sizes
   - Monitor for memory leaks in pipeline stages

2. **Database Connection Issues**
   - Verify Railway PostgreSQL connectivity
   - Check connection pool health: `GET /health/database`
   - Review connection pool settings

3. **High Error Rates**
   - Check feed health scores
   - Review circuit breaker states
   - Investigate pipeline stage errors

4. **Slow Processing**
   - Monitor system load metrics
   - Check for database performance issues
   - Review backpressure throttling

### Debug Commands

```bash
# View system status
python -c "
import asyncio
from main_production import ProductionRSSSystem
system = ProductionRSSSystem()
asyncio.run(system.initialize())
status = asyncio.run(system.get_system_status())
print(status)
"

# Monitor pipeline performance
python -c "
import asyncio
from monitoring import DashboardMetrics
# ... monitoring code
"
```

## 📚 API Reference

### Core Classes

- `ProductionRSSSystem`: Main system orchestrator
- `PipelineProcessor`: 8-stage processing pipeline
- `BatchPlanner`: Intelligent batch creation and scheduling
- `ConfigurationManager`: Hot-reload configuration system
- `ConnectionPoolManager`: Database/Redis connection management
- `BackpressureManager`: Throttling and load management

### Key Methods

```python
# System management
await system.initialize()
await system.run()
await system.shutdown()

# Batch processing
batch_id = await planner.create_batch(config, worker_id)
result = await processor.process_batch(batch_id, worker_id)

# Configuration
config = config_manager.get("pipeline.batch_size", default=200)
await config_manager.setup_ab_test(key, variants, traffic_split)
```

## 🔐 Security Considerations

1. **Database Security**: Uses SSL connections to Railway PostgreSQL
2. **Input Validation**: All data validated through Pydantic schemas
3. **Rate Limiting**: Per-domain throttling prevents abuse
4. **Circuit Breakers**: Protect against cascade failures
5. **Audit Logging**: All configuration changes logged
6. **Secret Management**: Environment-based secret handling

## 📋 Production Checklist

### Pre-Deployment
- [ ] Database schema deployed and verified
- [ ] Redis cluster configured and accessible
- [ ] Configuration validated and tested
- [ ] SSL certificates configured (if applicable)
- [ ] Monitoring dashboards deployed
- [ ] Alerting rules configured
- [ ] Backup procedures tested

### Go-Live
- [ ] Health checks passing
- [ ] Performance benchmarks met
- [ ] Error rates within acceptable limits
- [ ] Monitoring and alerting active
- [ ] Documentation updated
- [ ] Team trained on operations

### Post-Deployment
- [ ] Monitor system metrics for 24 hours
- [ ] Validate SLA compliance
- [ ] Review error logs and optimize
- [ ] Performance tuning based on real traffic
- [ ] Update monitoring thresholds if needed

---

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review system logs in `logs/rss_pipeline.log`
3. Monitor dashboards for system health
4. Contact system administrator

**System ID**: Check `system.system_id` for unique deployment identifier
**Version**: 1.0.0 Production
**Last Updated**: 2024-08-30
