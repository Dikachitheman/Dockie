"""
Optional Redis-backed cache helpers.

Falls back to a no-op backend when Redis is not configured or unavailable.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class CacheBackend(Protocol):
    async def get_json(self, key: str) -> Any | None: ...
    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    async def delete_key(self, key: str) -> None: ...
    async def delete_by_prefix(self, prefix: str) -> None: ...
    async def ping(self) -> bool: ...


class NullCacheBackend:
    async def get_json(self, key: str) -> Any | None:
        del key
        return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        del key, value, ttl_seconds

    async def delete_key(self, key: str) -> None:
        del key

    async def delete_by_prefix(self, prefix: str) -> None:
        del prefix

    async def ping(self) -> bool:
        return False


class RedisCacheBackend:
    def __init__(self, redis_url: str, prefix: str = "dockie") -> None:
        try:
            from redis.asyncio import Redis
        except ImportError as exc:
            raise RuntimeError("redis package is not installed") from exc

        self._prefix = prefix.rstrip(":")
        self._redis = Redis.from_url(redis_url, decode_responses=True)

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get_json(self, key: str) -> Any | None:
        raw = await self._redis.get(self._full_key(key))
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        await self._redis.set(self._full_key(key), json.dumps(value), ex=ttl_seconds)

    async def delete_key(self, key: str) -> None:
        await self._redis.delete(self._full_key(key))

    async def delete_by_prefix(self, prefix: str) -> None:
        pattern = self._full_key(f"{prefix}*")
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    async def ping(self) -> bool:
        return bool(await self._redis.ping())


@dataclass(slots=True)
class CacheLockLease:
    key: str
    token: str
    acquired: bool


class CacheCoordinator:
    _local_guard = asyncio.Lock()
    _local_leases: set[str] = set()

    def __init__(self, cache: CacheBackend) -> None:
        self._cache = cache
        self._redis = cache._redis if isinstance(cache, RedisCacheBackend) else None

    async def try_acquire(self, key: str, lease_seconds: int) -> CacheLockLease:
        token = uuid.uuid4().hex
        if self._redis is not None:
            acquired = bool(await self._redis.set(key, token, ex=lease_seconds, nx=True))
            return CacheLockLease(key=key, token=token, acquired=acquired)

        async with self._local_guard:
            if key in self._local_leases:
                return CacheLockLease(key=key, token=token, acquired=False)
            self._local_leases.add(key)
        return CacheLockLease(key=key, token=token, acquired=True)

    async def release(self, lease: CacheLockLease) -> None:
        if not lease.acquired:
            return

        if self._redis is not None:
            await self._redis.eval(
                """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                end
                return 0
                """,
                1,
                lease.key,
                lease.token,
            )
            return

        async with self._local_guard:
            self._local_leases.discard(lease.key)

    async def wait_for_json(
        self,
        cache_key: str,
        *,
        timeout_ms: int,
        poll_interval_ms: int,
    ) -> Any | None:
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        poll_interval_seconds = max(poll_interval_ms, 1) / 1000

        while asyncio.get_running_loop().time() < deadline:
            cached = await self._cache.get_json(cache_key)
            if cached is not None:
                return cached
            await asyncio.sleep(poll_interval_seconds)

        return await self._cache.get_json(cache_key)


@lru_cache
def get_cache_backend() -> CacheBackend:
    if not settings.cache_enabled or not settings.redis_url:
        logger.info("cache_backend_selected", backend="none")
        return NullCacheBackend()

    try:
        backend = RedisCacheBackend(settings.redis_url, prefix=settings.cache_prefix)
        logger.info("cache_backend_selected", backend="redis", prefix=settings.cache_prefix)
        return backend
    except Exception as exc:
        logger.warning("cache_backend_init_failed", error=str(exc))
        return NullCacheBackend()


async def invalidate_cache_prefix(prefix: str) -> None:
    try:
        await get_cache_backend().delete_by_prefix(prefix)
    except Exception as exc:
        logger.warning("cache_invalidation_failed", prefix=prefix, error=str(exc))


async def invalidate_shipment_cache(shipment_id: str) -> None:
    cache = get_cache_backend()
    try:
        await cache.delete_key(f"shipments:status:{shipment_id}")
        await cache.delete_key(f"shipments:history:{shipment_id}")
    except Exception as exc:
        logger.warning("shipment_cache_invalidation_failed", shipment_id=shipment_id, error=str(exc))


async def check_cache_connection() -> bool:
    try:
        return await get_cache_backend().ping()
    except Exception as exc:
        logger.warning("cache_ping_failed", error=str(exc))
        return False


def build_cache_coordinator(cache: CacheBackend | None = None) -> CacheCoordinator:
    return CacheCoordinator(cache or get_cache_backend())
