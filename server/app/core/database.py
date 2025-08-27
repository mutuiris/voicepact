import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import redis.asyncio as redis
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

Base = declarative_base()


class DatabaseManager:
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._redis_pool: Optional[redis.ConnectionPool] = None
        self._redis_client: Optional[redis.Redis] = None

    async def init_db(self):
        if settings.database_url.startswith("sqlite"):
            self._engine = create_async_engine(
                "sqlite+aiosqlite:///./voicepact.db",
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,
                },
                echo=settings.database_echo,
                future=True,
            )
            
            @event.listens_for(self._engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=-64000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=268435456")
                cursor.close()
        else:
            self._engine = create_async_engine(
                settings.database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=settings.database_echo,
            )

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        self._redis_pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        
        self._redis_client = redis.Redis(
            connection_pool=self._redis_pool,
            decode_responses=True,
        )

        await self._test_connections()

    async def _test_connections(self):
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

        try:
            await self._redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise

    async def create_tables(self):
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        if self._engine:
            await self._engine.dispose()
        if self._redis_client:
            await self._redis_client.close()
        if self._redis_pool:
            await self._redis_pool.disconnect()

    @property
    def engine(self) -> AsyncEngine:
        if not self._engine:
            raise RuntimeError("Database not initialized")
        return self._engine

    @property
    def redis(self) -> redis.Redis:
        if not self._redis_client:
            raise RuntimeError("Redis not initialized")
        return self._redis_client

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self._session_factory:
            raise RuntimeError("Database not initialized")
        
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_redis_session(self) -> redis.Redis:
        if not self._redis_client:
            raise RuntimeError("Redis not initialized")
        return self._redis_client


db_manager = DatabaseManager()


async def init_database():
    await db_manager.init_db()
    await db_manager.create_tables()


async def close_database():
    await db_manager.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.get_session() as session:
        yield session


async def get_redis() -> redis.Redis:
    return await db_manager.get_redis_session()


class CacheManager:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get(self, key: str) -> Optional[str]:
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(
        self, 
        key: str, 
        value: str, 
        expire: Optional[int] = None
    ) -> bool:
        try:
            if expire:
                return await self.redis.setex(key, expire, value)
            return await self.redis.set(key, value)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        try:
            return bool(await self.redis.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    async def increment(self, key: str) -> int:
        try:
            return await self.redis.incr(key)
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {e}")
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        try:
            return await self.redis.expire(key, seconds)
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False

    async def get_json(self, key: str) -> Optional[dict]:
        import json
        try:
            data = await self.get(key)
            return json.loads(data) if data else None
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"JSON decode error for key {key}: {e}")
            return None

    async def set_json(
        self, 
        key: str, 
        value: dict, 
        expire: Optional[int] = None
    ) -> bool:
        import json
        try:
            json_str = json.dumps(value)
            return await self.set(key, json_str, expire)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON encode error for key {key}: {e}")
            return False

    async def get_hash(self, key: str, field: str) -> Optional[str]:
        try:
            return await self.redis.hget(key, field)
        except Exception as e:
            logger.error(f"Hash get error for {key}.{field}: {e}")
            return None

    async def set_hash(self, key: str, field: str, value: str) -> bool:
        try:
            return bool(await self.redis.hset(key, field, value))
        except Exception as e:
            logger.error(f"Hash set error for {key}.{field}: {e}")
            return False

    async def get_all_hash(self, key: str) -> dict:
        try:
            return await self.redis.hgetall(key) or {}
        except Exception as e:
            logger.error(f"Hash get all error for key {key}: {e}")
            return {}

    async def delete_hash_field(self, key: str, field: str) -> bool:
        try:
            return bool(await self.redis.hdel(key, field))
        except Exception as e:
            logger.error(f"Hash delete error for {key}.{field}: {e}")
            return False


cache_manager = None


async def get_cache() -> CacheManager:
    global cache_manager
    if not cache_manager:
        redis_client = await get_redis()
        cache_manager = CacheManager(redis_client)
    return cache_manager


class SessionManager:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.session_prefix = "session:"
        self.default_ttl = 3600

    async def create_session(
        self, 
        session_id: str, 
        data: dict, 
        ttl: Optional[int] = None
    ) -> bool:
        try:
            import json
            session_key = f"{self.session_prefix}{session_id}"
            session_data = json.dumps(data)
            expire_time = ttl or self.default_ttl
            return await self.redis.setex(session_key, expire_time, session_data)
        except Exception as e:
            logger.error(f"Session create error for {session_id}: {e}")
            return False

    async def get_session(self, session_id: str) -> Optional[dict]:
        try:
            import json
            session_key = f"{self.session_prefix}{session_id}"
            data = await self.redis.get(session_key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Session get error for {session_id}: {e}")
            return None

    async def update_session(
        self, 
        session_id: str, 
        data: dict, 
        extend_ttl: bool = True
    ) -> bool:
        try:
            import json
            session_key = f"{self.session_prefix}{session_id}"
            session_data = json.dumps(data)
            
            if extend_ttl:
                return await self.redis.setex(session_key, self.default_ttl, session_data)
            else:
                return await self.redis.set(session_key, session_data, keepttl=True)
        except Exception as e:
            logger.error(f"Session update error for {session_id}: {e}")
            return False

    async def delete_session(self, session_id: str) -> bool:
        try:
            session_key = f"{self.session_prefix}{session_id}"
            return bool(await self.redis.delete(session_key))
        except Exception as e:
            logger.error(f"Session delete error for {session_id}: {e}")
            return False

    async def extend_session(self, session_id: str, ttl: Optional[int] = None) -> bool:
        try:
            session_key = f"{self.session_prefix}{session_id}"
            expire_time = ttl or self.default_ttl
            return await self.redis.expire(session_key, expire_time)
        except Exception as e:
            logger.error(f"Session extend error for {session_id}: {e}")
            return False


session_manager = None


async def get_session_manager() -> SessionManager:
    global session_manager
    if not session_manager:
        redis_client = await get_redis()
        session_manager = SessionManager(redis_client)
    return session_manager


async def health_check() -> dict:
    health = {
        "database": "unknown",
        "redis": "unknown",
    }
    
    try:
        async with db_manager.get_session() as session:
            await session.execute(text("SELECT 1"))
        health["database"] = "healthy"
    except Exception as e:
        health["database"] = f"error: {str(e)}"
        logger.error(f"Database health check failed: {e}")
    
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        health["redis"] = "healthy"
    except Exception as e:
        health["redis"] = f"error: {str(e)}"
        logger.error(f"Redis health check failed: {e}")
    
    return health