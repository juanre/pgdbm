# Migrating to pgdbm from Other ORMs/Patterns

This guide helps you migrate from popular ORMs and database patterns to pgdbm's efficient, PostgreSQL-native approach.

## Table of Contents
- [From SQLAlchemy](#from-sqlalchemy)
- [From Django ORM](#from-django-orm)
- [From TypeORM (Node.js)](#from-typeorm)
- [From Raw SQL](#from-raw-sql)
- [From Multiple Connection Patterns](#from-multiple-connections)
- [Migration Checklist](#migration-checklist)

## From SQLAlchemy

### SQLAlchemy Pattern
```python
# SQLAlchemy typical setup
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    name = Column(String)

engine = create_engine('postgresql://localhost/myapp')
Session = sessionmaker(bind=engine)

# Usage
session = Session()
user = User(email='test@example.com', name='Test User')
session.add(user)
session.commit()
```

### pgdbm Equivalent
```python
# pgdbm approach - no ORM overhead, direct SQL
from pgdbm import AsyncDatabaseManager, DatabaseConfig

# Setup (once at startup)
config = DatabaseConfig(connection_string='postgresql://localhost/myapp')
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
db = AsyncDatabaseManager(pool=shared_pool, schema='public')

# Migration file: migrations/001_users.sql
"""
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255)
);
"""

# Usage - direct SQL with type safety
user_id = await db.fetch_value(
    "INSERT INTO {{tables.users}} (email, name) VALUES ($1, $2) RETURNING id",
    'test@example.com', 'Test User'
)

# Query with results
users = await db.fetch_all("SELECT * FROM {{tables.users}}")
```

### Key Differences

| SQLAlchemy | pgdbm |
|------------|-------|
| ORM with models | Direct SQL with templates |
| Synchronous by default | Async-first |
| Session management | Connection pooling |
| Lazy loading issues | Explicit queries |
| Complex for raw SQL | SQL-first design |

### Migration Steps

1. **Replace Models with Migrations**
   ```python
   # Instead of SQLAlchemy models, create SQL migrations
   # migrations/001_initial.sql
   CREATE TABLE IF NOT EXISTS {{tables.users}} (
       id SERIAL PRIMARY KEY,
       email VARCHAR(255) UNIQUE NOT NULL,
       created_at TIMESTAMP DEFAULT NOW()
   );
   ```

2. **Replace Session with Database Manager**
   ```python
   # SQLAlchemy
   with Session() as session:
       session.query(User).filter_by(email=email).first()

   # pgdbm
   user = await db.fetch_one(
       "SELECT * FROM {{tables.users}} WHERE email = $1",
       email
   )
   ```

3. **Replace Relationships with Joins**
   ```python
   # SQLAlchemy lazy loading
   user.orders  # Triggers additional query

   # pgdbm explicit join
   user_with_orders = await db.fetch_one("""
       SELECT u.*, array_agg(o.*) as orders
       FROM {{tables.users}} u
       LEFT JOIN {{tables.orders}} o ON o.user_id = u.id
       WHERE u.id = $1
       GROUP BY u.id
   """, user_id)
   ```

## From Django ORM

### Django Pattern
```python
# Django models.py
from django.db import models

class User(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'users'

# Usage
user = User.objects.create(email='test@example.com', name='Test')
active_users = User.objects.filter(is_active=True)
```

### pgdbm Equivalent
```python
# pgdbm service
class UserService:
    def __init__(self, db: AsyncDatabaseManager):
        self.db = db

    async def create_user(self, email: str, name: str) -> int:
        return await self.db.fetch_value(
            """INSERT INTO {{tables.users}} (email, name, is_active)
               VALUES ($1, $2, true) RETURNING id""",
            email, name
        )

    async def get_active_users(self):
        return await self.db.fetch_all(
            "SELECT * FROM {{tables.users}} WHERE is_active = true"
        )
```

### Migration Steps

1. **Convert Django Migrations to SQL**
   ```python
   # Django migration
   migrations.CreateModel(
       name='User',
       fields=[
           ('id', models.AutoField(primary_key=True)),
           ('email', models.EmailField(unique=True)),
       ],
   )

   # pgdbm migration
   CREATE TABLE IF NOT EXISTS {{tables.users}} (
       id SERIAL PRIMARY KEY,
       email VARCHAR(255) UNIQUE NOT NULL
   );
   ```

2. **Replace QuerySets with Service Methods**
   ```python
   # Django
   User.objects.filter(created_at__gte=date).count()

   # pgdbm
   count = await db.fetch_value(
       "SELECT COUNT(*) FROM {{tables.users}} WHERE created_at >= $1",
       date
   )
   ```

3. **Handle Transactions Explicitly**
   ```python
   # Django
   with transaction.atomic():
       user.save()
       profile.save()

   # pgdbm
   async with db.transaction():
       await db.execute("INSERT INTO {{tables.users}} ...")
       await db.execute("INSERT INTO {{tables.profiles}} ...")
   ```

## From TypeORM

### TypeORM Pattern
```typescript
// TypeORM entity
@Entity()
export class User {
    @PrimaryGeneratedColumn()
    id: number;

    @Column({ unique: true })
    email: string;

    @Column()
    name: string;
}

// Usage
const userRepository = getRepository(User);
const user = await userRepository.save({ email, name });
```

### pgdbm Equivalent
```python
# Python with pgdbm
async def create_user(email: str, name: str) -> dict:
    return await db.fetch_one(
        """INSERT INTO {{tables.users}} (email, name)
           VALUES ($1, $2)
           RETURNING id, email, name""",
        email, name
    )
```

## From Raw SQL

If you're using raw SQL with poor connection management:

### Before (Common Anti-Pattern)
```python
import psycopg2

def get_user(user_id):
    # Creating new connection per request (BAD!)
    conn = psycopg2.connect("postgresql://localhost/myapp")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    conn.close()  # Connection overhead every time
    return result
```

### After (pgdbm Pattern)
```python
# One-time setup
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
db = AsyncDatabaseManager(pool=shared_pool, schema='public')

# Reuse connections from pool
async def get_user(user_id):
    return await db.fetch_one(
        "SELECT * FROM {{tables.users}} WHERE id = $1",
        user_id
    )
```

## From Multiple Connections

### Before (Multiple Connections Anti-Pattern)
```python
# Each service creates its own connection/pool
class UserService:
    def __init__(self):
        self.conn = psycopg2.connect("postgresql://localhost/myapp")

class OrderService:
    def __init__(self):
        self.conn = psycopg2.connect("postgresql://localhost/myapp")  # Duplicate!

class BillingService:
    def __init__(self):
        self.conn = psycopg2.connect("postgresql://localhost/myapp")  # Duplicate!
```

### After (Shared Pool Pattern)
```python
# Shared infrastructure
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

# Each service uses the shared pool with its own schema
user_service = UserService(
    AsyncDatabaseManager(pool=shared_pool, schema='users')
)
order_service = OrderService(
    AsyncDatabaseManager(pool=shared_pool, schema='orders')
)
billing_service = BillingService(
    AsyncDatabaseManager(pool=shared_pool, schema='billing')
)
```

## Migration Checklist

### Phase 1: Planning
- [ ] Inventory all database connections in your application
- [ ] Identify services that can share a connection pool
- [ ] Plan schema organization (one per service recommended)
- [ ] Review existing migrations and convert to SQL

### Phase 2: Setup
- [ ] Install pgdbm: `pip install pgdbm`
- [ ] Create database configuration
- [ ] Set up shared connection pool
- [ ] Create schema-specific managers

### Phase 3: Migration
- [ ] Convert ORM models to SQL migrations
- [ ] Replace ORM queries with SQL queries
- [ ] Use `{{tables.tablename}}` syntax for schema isolation
- [ ] Implement service layer for business logic
- [ ] Add proper error handling

### Phase 4: Testing
- [ ] Test connection pool behavior under load
- [ ] Verify transaction handling
- [ ] Check query performance
- [ ] Test migration rollback scenarios

### Phase 5: Optimization
- [ ] Enable query monitoring
- [ ] Add prepared statements for repeated queries
- [ ] Implement connection pool monitoring
- [ ] Add health checks

## Common Gotchas and Solutions

### 1. N+1 Query Problem
**ORM Problem**: Lazy loading causes multiple queries
```python
# ORM - causes N+1 queries
users = User.objects.all()
for user in users:
    print(user.orders.count())  # Additional query per user!
```

**pgdbm Solution**: Use explicit joins
```python
# Single query with aggregation
users_with_counts = await db.fetch_all("""
    SELECT u.*, COUNT(o.id) as order_count
    FROM {{tables.users}} u
    LEFT JOIN {{tables.orders}} o ON o.user_id = u.id
    GROUP BY u.id
""")
```

### 2. Connection Exhaustion
**Problem**: Creating connections per request
```python
# Bad - new connection each time
def handle_request():
    conn = create_connection()
    # ... do work
    conn.close()
```

**Solution**: Use shared pool
```python
# Good - reuse from pool
async def handle_request(db: DatabaseDep):
    result = await db.fetch_one(...)
```

### 3. Missing Indexes
**Problem**: ORMs often miss optimal indexes
```python
# ORM might not create optimal indexes
User.objects.filter(created_at__gte=date, is_active=True)
```

**Solution**: Explicit index creation
```sql
-- In migration file
CREATE INDEX IF NOT EXISTS users_active_recent
ON {{tables.users}} (created_at DESC)
WHERE is_active = true;
```

### 4. Transaction Scope
**Problem**: ORM implicit transactions
```python
# Django - implicit transaction
user.save()  # When does this commit?
```

**Solution**: Explicit transaction control
```python
# pgdbm - explicit and clear
async with db.transaction():
    await db.execute(...)  # All or nothing
```

## Performance Comparison

| Operation | ORM (typical) | pgdbm |
|-----------|--------------|-------|
| Simple INSERT | 5-10ms | 1-2ms |
| Complex JOIN | 50-100ms | 10-20ms |
| Bulk INSERT (1000 rows) | 500-1000ms | 50-100ms |
| Connection overhead | High (per request) | Low (pooled) |
| Memory usage | High (objects) | Low (tuples) |

## Best Practices After Migration

1. **Use Service Layer**: Encapsulate database logic in service classes
2. **Leverage PostgreSQL Features**: Use JSONB, arrays, CTEs, window functions
3. **Monitor Everything**: Track slow queries, pool usage, connection counts
4. **Test with Load**: Ensure pool sizing is appropriate for your load
5. **Document Schemas**: Keep schema documentation up to date

## Getting Help

- Review [Production Patterns Guide](./production-patterns.md)
- Check [Quick Reference](./quick-reference.md)
- See [Examples](../examples/) for working code
- Read [API Reference](./api-reference.md) for detailed usage

## Summary

Migrating to pgdbm from ORMs provides:
- **Better Performance**: Direct SQL, no ORM overhead
- **Clear SQL**: See exactly what queries run
- **PostgreSQL Power**: Use all PostgreSQL features
- **Connection Efficiency**: Shared pools prevent exhaustion
- **Schema Isolation**: Clean service separation
- **Type Safety**: With Python type hints and Pydantic

The key is to embrace SQL rather than hide from it, while using pgdbm's patterns to maintain clean, maintainable code.
