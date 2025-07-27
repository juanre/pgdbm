# Installation

## Requirements

- Python 3.9+
- PostgreSQL 12+
- asyncpg (installed automatically)

## Install

```bash
# Basic installation
uv add pgdbm

# or

pip install pgdbm

# With development tools
pip install pgdbm[dev]
```

## Verify Installation

```python
import asyncio
from pgdbm import AsyncDatabaseManager, DatabaseConfig

async def verify():
    config = DatabaseConfig(
        host="localhost",
        database="postgres",
        user="postgres",
        password="postgres"
    )

    db = AsyncDatabaseManager(config)
    await db.connect()

    version = await db.fetch_value("SELECT version()")
    print(f"Connected to: {version}")

    await db.disconnect()

asyncio.run(verify())
```

## Troubleshooting

**asyncpg compilation errors**: Install Python development headers
- Ubuntu: `sudo apt install python3-dev`
- macOS: `xcode-select --install`

**Connection refused**: Check PostgreSQL is running with `pg_isready`

**Permission denied**: Ensure your database user has CREATE SCHEMA privileges

For more help, see [GitHub Issues](https://github.com/yourusername/pgdbm/issues).
