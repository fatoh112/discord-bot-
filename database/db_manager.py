import os
import asyncio
import aiosqlite
from typing import AsyncGenerator, Optional, Any, List, Dict, Tuple
from contextlib import asynccontextmanager
from loguru import logger

class DatabaseManager:
    """Async database manager wrapping aiosqlite with connection pooling and transactions."""

    def __init__(self, db_path: str = "database.db", max_connections: int = 5):
        self.db_path = db_path
        self.max_connections = max_connections
        self.pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()
        self.connections: List[aiosqlite.Connection] = []
        self._connected: bool = False

    async def connect(self) -> None:
        """Initializes the connection pool and applies standard SQLite settings."""
        if self._connected:
            return

        for _ in range(self.max_connections):
            try:
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
                # Configure performance and behavior optimizations
                await conn.execute("PRAGMA foreign_keys = ON;")
                await conn.execute("PRAGMA journal_mode = WAL;")
                await conn.execute("PRAGMA synchronous = NORMAL;")
                self.connections.append(conn)
                await self.pool.put(conn)
            except Exception as e:
                logger.error(f"Failed to create connection for SQLite pool: {e}")
                # Clean up any connections already created
                for c in self.connections:
                    await c.close()
                self.connections.clear()
                raise e

        self._connected = True
        logger.info(f"Database connection pool initialized with {len(self.connections)} connections.")

    async def disconnect(self) -> None:
        """Closes all connections in the pool gracefully."""
        if not self._connected:
            return

        for conn in self.connections:
            try:
                await conn.close()
            except Exception as e:
                logger.error(f"Error closing connection during pool teardown: {e}")

        self.connections.clear()
        self.pool = asyncio.Queue()
        self._connected = False
        logger.info("Database connection pool closed.")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Context manager to lease a connection from the pool and return it on completion."""
        if not self._connected:
            await self.connect()

        conn = await self.pool.get()
        try:
            yield conn
        finally:
            await self.pool.put(conn)

    @asynccontextmanager
    async def begin_transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Provides an atomic transaction wrapper on an acquired connection."""
        async with self.acquire() as conn:
            await conn.execute("BEGIN TRANSACTION;")
            try:
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                logger.error(f"Database transaction failed. Changes rolled back. Error: {e}")
                raise e

    async def execute(self, query: str, parameters: Optional[Tuple[Any, ...]] = None) -> int:
        """Executes a command (INSERT, UPDATE, DELETE). Returns affected rowcount."""
        try:
            async with self.acquire() as conn:
                async with conn.execute(query, parameters or ()) as cursor:
                    await conn.commit()
                    return cursor.rowcount
        except Exception as e:
            logger.error(f"Database execute error. Query: {query} | Error: {e}")
            raise e

    async def fetchone(self, query: str, parameters: Optional[Tuple[Any, ...]] = None) -> Optional[aiosqlite.Row]:
        """Fetches a single row matching query criteria."""
        try:
            async with self.acquire() as conn:
                async with conn.execute(query, parameters or ()) as cursor:
                    return await cursor.fetchone()
        except Exception as e:
            logger.error(f"Database fetchone error. Query: {query} | Error: {e}")
            raise e

    async def fetchall(self, query: str, parameters: Optional[Tuple[Any, ...]] = None) -> List[aiosqlite.Row]:
        """Fetches all rows matching query criteria."""
        try:
            async with self.acquire() as conn:
                async with conn.execute(query, parameters or ()) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Database fetchall error. Query: {query} | Error: {e}")
            raise e

    async def run_migrations(self, migrations_dir: str = "database/migrations") -> None:
        """Applies SQL migration files sequentially from migrations directory."""
        # Ensure target schema version tracker is present
        await self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT
            );
            """
        )

        applied_rows = await self.fetchall("SELECT version FROM schema_version")
        applied_versions = {row["version"] for row in applied_rows}

        if not os.path.exists(migrations_dir):
            os.makedirs(migrations_dir, exist_ok=True)
            logger.warning(f"Migrations directory '{migrations_dir}' was missing and has been created.")
            return

        migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])
        for filename in migration_files:
            try:
                version = int(filename.split("_")[0])
            except ValueError:
                logger.warning(f"Skipping migration file with invalid name format: {filename}")
                continue

            if version in applied_versions:
                continue

            filepath = os.path.join(migrations_dir, filename)
            logger.info(f"Applying schema migration: {filename}")
            
            with open(filepath, "r", encoding="utf-8") as f:
                schema_sql = f.read()

            try:
                async with self.begin_transaction() as conn:
                    await conn.executescript(schema_sql)
                    await conn.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES (?, datetime('now'))",
                        (version,)
                    )
                logger.info(f"Successfully applied migration: {filename}")
            except Exception as e:
                logger.error(f"Critical error applying database migration {filename}: {e}")
                raise e
