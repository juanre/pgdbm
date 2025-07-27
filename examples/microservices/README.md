# Microservices Example

A complete microservices architecture demonstrating shared database connection pools with schema-based service isolation using pgdbm.

## Architecture

This example shows how to build a microservices system where:
- Multiple services share a single database connection pool
- Each service uses its own PostgreSQL schema for table isolation
- Services communicate via REST APIs and message queues
- Database connections are efficiently managed across services
- Each service maintains its own domain logic and migrations

## Services

### 1. Gateway Service (Port 8000)
- API gateway that routes requests to appropriate services
- Manages authentication and rate limiting
- Provides unified API interface

### 2. User Service (Port 8001)
- User registration and authentication
- Profile management
- JWT token generation
- **Schema**: `users`

### 3. Order Service (Port 8002)
- Order creation and management
- Order status tracking
- Inventory validation
- **Schema**: `orders`

### 4. Inventory Service (Port 8003)
- Product catalog management
- Stock tracking
- Inventory updates
- **Schema**: `inventory`

### 5. Notification Service (Port 8004)
- Email/SMS notifications
- Event-driven messaging
- Notification templates

## Shared Components

### Database Manager
A shared database connection pool that all services connect to:

```python
# shared/database.py
class SharedDatabaseManager:
    _instance = None
    _db_manager = None

    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance.initialize()
        return cls._instance
```

### Message Queue
Services communicate asynchronously via a message queue pattern.

## Project Structure

```
microservices/
├── README.md
├── docker-compose.yml
├── requirements.txt
├── migrations/
│   └── 001_shared_tables.sql    # Shared tables only
├── shared/
│   ├── __init__.py
│   ├── database.py      # Shared database manager
│   ├── events.py        # Event system
│   └── models.py        # Shared data models
├── gateway/
│   ├── __init__.py
│   ├── main.py
│   └── routes.py
├── services/
│   ├── __init__.py
│   ├── users/           # User service (schema: users)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api.py
│   │   ├── db.py
│   │   ├── models.py
│   │   └── migrations/
│   │       └── 001_users_schema.sql
│   ├── orders/          # Order service (schema: orders)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api.py
│   │   ├── db.py
│   │   ├── models.py
│   │   └── migrations/
│   │       └── 001_orders_schema.sql
│   ├── inventory/       # Inventory service (schema: inventory)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api.py
│   │   ├── db.py
│   │   ├── models.py
│   │   └── migrations/
│   │       └── 001_inventory_schema.sql
│   └── notification/
│       ├── __init__.py
│       ├── main.py
│       ├── handlers.py
│       └── templates.py
└── tests/
    ├── conftest.py
    ├── test_integration.py
    └── test_services.py
```

## Running the System

### With Docker Compose (Recommended)

```bash
docker-compose up
```

### Manually

1. Start PostgreSQL:
```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
```

2. Run migrations:
```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost/microservices"
python -m shared.database migrate
```

3. Start each service:
```bash
# Terminal 1 - Gateway
python -m gateway.main

# Terminal 2 - User Service
python -m services.user.main

# Terminal 3 - Order Service
python -m services.order.main

# Terminal 4 - Inventory Service
python -m services.inventory.main

# Terminal 5 - Notification Service
python -m services.notification.main
```

## API Examples

### Create User
```bash
curl -X POST http://localhost:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "name": "John Doe"}'
```

### Create Order
```bash
curl -X POST http://localhost:8000/api/orders \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"product_id": "123", "quantity": 2}
    ]
  }'
```

### Check Inventory
```bash
curl http://localhost:8000/api/inventory/products/123
```

## Key Patterns Demonstrated

### 1. Schema-Based Service Isolation

Each service uses its own PostgreSQL schema to prevent table name conflicts:

```python
class ServiceDatabase:
    def __init__(self, service_name: str, schema_name: str):
        self.service_name = service_name
        self.schema_name = schema_name

    async def initialize(self):
        shared = await SharedDatabaseManager.get_instance()
        # Create schema-isolated database manager
        self.db = AsyncDatabaseManager(
            pool=shared._db_manager.pool,
            schema=self.schema_name
        )
```

This allows each service to have its own `users` table, `products` table, etc., without conflicts.

### 2. Shared Connection Pool

All services share a single database connection pool to avoid connection exhaustion, even though they use different schemas:

```python
# Shared pool created once
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

# Each service uses the same pool with different schemas
user_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
order_db = AsyncDatabaseManager(pool=shared_pool, schema="orders")
```

### 3. Event-Driven Communication

Services communicate via events to maintain loose coupling:

```python
# Order service publishes event
await event_bus.publish("order.created", {
    "order_id": order.id,
    "user_id": user_id,
    "total": total
})

# Notification service handles event
@event_handler("order.created")
async def handle_order_created(event_data):
    await send_order_confirmation(event_data)
```

### 4. Service Discovery

Services register themselves and discover others:

```python
# Service registration
await service_registry.register("user-service", "http://localhost:8001")

# Service discovery
user_service_url = await service_registry.discover("user-service")
```

### 5. Circuit Breaker

Resilient inter-service communication:

```python
@circuit_breaker(failure_threshold=5, recovery_timeout=60)
async def call_inventory_service(product_id):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{inventory_url}/products/{product_id}")
        return response.json()
```

## Testing

### Unit Tests
```bash
pytest tests/test_services.py
```

### Integration Tests
```bash
pytest tests/test_integration.py
```

### Load Testing
```bash
locust -f tests/locustfile.py
```

## Monitoring

- Health checks at `/health` for each service
- Prometheus metrics at `/metrics`
- Distributed tracing with OpenTelemetry
- Centralized logging

## Production Considerations

1. **Connection Pool Sizing** - Configure based on total service count
2. **Service Mesh** - Consider Istio/Linkerd for production
3. **Message Queue** - Use RabbitMQ/Kafka for reliable messaging
4. **Caching** - Add Redis for shared caching layer
5. **API Gateway** - Use Kong/Traefik for production gateway
