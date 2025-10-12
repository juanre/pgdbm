# Production-Ready pgdbm Application

This example demonstrates all pgdbm best practices in a production-ready application with:

- ✅ Shared connection pool pattern
- ✅ Schema-based service isolation
- ✅ FastAPI dependency injection
- ✅ Proper error handling
- ✅ Health checks and monitoring
- ✅ Comprehensive testing
- ✅ Docker support
- ✅ Environment-based configuration

## Architecture

```
production-app/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application with lifespan
│   ├── config.py            # Configuration management
│   ├── database.py          # Database infrastructure
│   ├── dependencies.py      # FastAPI dependencies
│   ├── models/              # Pydantic models
│   ├── services/            # Business logic services
│   │   ├── users.py        # User service
│   │   ├── orders.py       # Order service
│   │   └── analytics.py    # Analytics service
│   └── routers/            # API endpoints
│       ├── users.py
│       ├── orders.py
│       ├── analytics.py
│       └── health.py
├── migrations/             # Database migrations
│   ├── users/
│   │   └── 001_initial.sql
│   ├── orders/
│   │   └── 001_initial.sql
│   └── analytics/
│       └── 001_initial.sql
├── tests/
│   ├── conftest.py        # Test fixtures
│   ├── test_users.py
│   ├── test_orders.py
│   └── test_integration.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
└── README.md
```

## Quick Start

### 1. Setup Environment

```bash
# Copy environment file
cp .env.example .env

# Edit .env with your database settings
# Or use Docker Compose for local development
```

### 2. Run with Docker

```bash
# Start PostgreSQL and the application
docker-compose up

# Application will be available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 3. Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL (if not using Docker)
# Update .env with connection details

# Run the application
uvicorn app.main:app --reload
```

## Key Features

### 1. Shared Connection Pool

All services share a single connection pool for efficiency:

```python
# One pool, multiple services
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
users_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
orders_db = AsyncDatabaseManager(pool=shared_pool, schema="orders")
```

### 2. Schema Isolation

Each service has its own schema for logical separation:

- `users` schema - User management
- `orders` schema - Order processing
- `analytics` schema - Analytics and reporting

### 3. Dependency Injection

Clean FastAPI dependency injection:

```python
@router.post("/users")
async def create_user(
    user: UserCreate,
    db: UserDatabase = Depends(get_user_db),
):
    return await db.create_user(user)
```

### 4. Health Checks

Comprehensive health monitoring:

- `/health` - Basic health check
- `/health/ready` - Readiness probe (database connectivity)
- `/health/live` - Liveness probe

### 5. Error Handling

Proper error handling with custom exceptions:

```python
try:
    user = await db.get_user(user_id)
except UserNotFoundError:
    raise HTTPException(404, "User not found")
```

### 6. Testing

Complete test coverage with fixtures:

```bash
# Run tests
pytest

# With coverage
pytest --cov=app --cov-report=html
```

## API Endpoints

### Users Service

- `POST /api/v1/users` - Create user
- `GET /api/v1/users/{id}` - Get user
- `PUT /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user
- `GET /api/v1/users` - List users

### Orders Service

- `POST /api/v1/orders` - Create order
- `GET /api/v1/orders/{id}` - Get order
- `PUT /api/v1/orders/{id}/status` - Update order status
- `GET /api/v1/orders` - List orders

### Analytics Service

- `GET /api/v1/analytics/users/stats` - User statistics
- `GET /api/v1/analytics/orders/stats` - Order statistics
- `GET /api/v1/analytics/revenue` - Revenue analytics

## Production Deployment

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname
DATABASE_MIN_CONNECTIONS=20
DATABASE_MAX_CONNECTIONS=100

# Application
APP_ENV=production
APP_DEBUG=false
APP_LOG_LEVEL=info

# Security
SECRET_KEY=your-secret-key-here
CORS_ORIGINS=https://yourdomain.com

# Monitoring
SLOW_QUERY_THRESHOLD_MS=1000
ENABLE_METRICS=true
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes Deployment

See `k8s/` directory for Kubernetes manifests with:
- Deployment with proper resource limits
- Service for load balancing
- ConfigMap for configuration
- Secret for sensitive data
- HorizontalPodAutoscaler for scaling

## Monitoring

### Metrics

The application exposes Prometheus metrics at `/metrics`:

- Connection pool utilization
- Query execution times
- Request latencies
- Error rates

### Logging

Structured logging with correlation IDs:

```python
logger.info("User created", extra={
    "user_id": user.id,
    "correlation_id": request.state.correlation_id,
})
```

## Performance

### Connection Pool Tuning

```python
config = DatabaseConfig(
    connection_string=settings.database_url,
    min_connections=20,      # Baseline connections
    max_connections=100,     # Maximum under load
    command_timeout=30.0,    # Query timeout
    statement_cache_size=1000,  # Prepared statements
)
```

### Query Optimization

- Prepared statements for repeated queries
- Batch operations where possible
- Proper indexing (see migrations)
- Connection pool monitoring

## Security

- SQL injection prevention via parameterized queries
- Schema isolation for multi-tenancy
- Environment-based secrets
- CORS configuration
- Rate limiting ready

## Contributing

1. Follow the established patterns
2. Add tests for new features
3. Update documentation
4. Run linting and type checking

## License

MIT
