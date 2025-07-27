# pgdbm Examples

This directory contains example projects demonstrating real-world usage patterns for pgdbm.

## Examples

### 1. [todo-app](./todo-app/)
A REST API for a todo application demonstrating:
- Service database wrapper pattern
- RESTful API with FastAPI
- Database migrations
- Testing
- Error handling
- CRUD operations

### 2. [multi-tenant-saas](./multi-tenant-saas/)
Multi-tenant SaaS application showing:
- Schema-based tenant isolation
- Dynamic tenant provisioning
- Tenant-specific migrations
- Cross-tenant queries (admin)
- Testing multi-tenant scenarios

### 3. [microservices](./microservices/)
Microservices architecture demonstrating:
- Shared connection pool across services
- Service-specific schemas
- Inter-service data access patterns
- Distributed testing
- Health checks and monitoring

## Running the Examples

Each example has its own README with specific instructions, but the general pattern is:

1. Create a PostgreSQL database
2. Set the `DATABASE_URL` environment variable
3. Install dependencies: `pip install -r requirements.txt`
4. Run migrations: `python -m app.db migrate`
5. Run the application: `python -m app.main`
6. Run tests: `pytest`

## Learning Path

1. **Start with todo-app** - Learn the basic patterns
2. **Move to multi-tenant-saas** - Understand schema isolation
3. **Explore microservices** - See advanced connection sharing

Each example builds on the previous one, introducing new concepts while reinforcing core patterns.
