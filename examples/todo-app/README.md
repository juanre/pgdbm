# Todo App Example

A complete REST API for a todo application demonstrating best practices for using pgdbm.

## Running from pgdbm Repository

If you're running this example from the pgdbm repository (before it's published to PyPI):

```bash
# From the todo-app directory
cd examples/todo-app

# Install dependencies (excluding pgdbm which we'll use locally)
pip install fastapi uvicorn pydantic python-dotenv pytest pytest-asyncio pytest-cov httpx

# Add pgdbm to Python path
export PYTHONPATH="../../src:$PYTHONPATH"

# Or run with:
PYTHONPATH="../../src:$PYTHONPATH" python -m app.main
```

## Features

- ✅ RESTful API with FastAPI
- ✅ Service database wrapper pattern
- ✅ Database migrations
- ✅ Comprehensive error handling
- ✅ Full test coverage
- ✅ Type safety with Pydantic
- ✅ Health checks
- ✅ Pagination support

## Project Structure

```
todo-app/
├── README.md
├── requirements.txt
├── migrations/
│   └── 001_initial_schema.sql
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration
│   ├── db.py            # Database wrapper
│   ├── models.py        # Pydantic models
│   └── api/
│       ├── __init__.py
│       ├── todos.py     # Todo endpoints
│       └── health.py    # Health check endpoints
└── tests/
    ├── conftest.py      # Test fixtures
    ├── test_api.py      # API tests
    └── test_db.py       # Database tests
```

## Setup

1. Create a PostgreSQL database:
```bash
createdb todo_app
```

2. Set environment variables:
```bash
export DATABASE_URL="postgresql://user:password@localhost/todo_app"
export APP_ENV="development"
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run migrations:
```bash
python -m app.db migrate
```

5. Run the application:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

### Todos

- `GET /api/todos` - List todos (with pagination)
- `POST /api/todos` - Create a new todo
- `GET /api/todos/{todo_id}` - Get a specific todo
- `PUT /api/todos/{todo_id}` - Update a todo
- `DELETE /api/todos/{todo_id}` - Delete a todo
- `POST /api/todos/{todo_id}/complete` - Mark todo as complete

### Health

- `GET /health` - Basic health check
- `GET /health/ready` - Readiness probe (checks database)

## Testing

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## Example Usage

### Create a todo
```bash
curl -X POST http://localhost:8000/api/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Learn pgdbm", "description": "Complete the tutorial"}'
```

### List todos
```bash
curl http://localhost:8000/api/todos?limit=10&offset=0
```

### Complete a todo
```bash
curl -X POST http://localhost:8000/api/todos/123/complete
```

## Key Patterns Demonstrated

1. **Service Database Wrapper** - See `app/db.py` for how to wrap pgdbm
2. **Error Handling** - Custom exceptions and proper HTTP status codes
3. **Testing** - Layered fixtures building on pgdbm's test infrastructure
4. **Migrations** - Schema versioning with automatic ordering
5. **Type Safety** - Pydantic models for request/response validation
6. **Configuration** - Environment-based configuration with validation
