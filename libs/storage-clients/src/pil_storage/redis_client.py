# ruff: noqa: UP040
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from collections.abc import Awaitable

RedisScalar: TypeAlias = bytes | bytearray | memoryview | str | int | float
RedisStreamFields: TypeAlias = dict[RedisScalar, RedisScalar]
RedisReadStreams: TypeAlias = dict[bytes | str | memoryview, int | bytes | str | memoryview]


@dataclass
class RedisClient:
    url: str
    password: str | None = None

    def __post_init__(self) -> None:
        self._pool = aioredis.ConnectionPool.from_url(
            self.url,
            password=self.password,
            decode_responses=True,
            max_connections=20,
        )
        self._redis = aioredis.Redis(connection_pool=self._pool)

    @property
    def r(self) -> aioredis.Redis:
        return self._redis

    async def xadd(self, stream: str, fields: dict[str, str]) -> str:
        stream_id = await self._redis.xadd(stream, cast("RedisStreamFields", fields))
        return str(stream_id)

    async def xread_group(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int = 10,
        block: int = 5000,
    ) -> list[Any]:
        entries = await self._redis.xreadgroup(
            group, consumer, cast("RedisReadStreams", streams), count=count, block=block
        )
        return cast("list[Any]", entries)

    async def xack(self, stream: str, group: str, *ids: str) -> int:
        return int(await cast("Awaitable[int]", self._redis.xack(stream, group, *ids)))

    async def ping(self) -> bool:
        return bool(await cast("Awaitable[bool]", self._redis.ping()))

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = await cast("Awaitable[list[Any]]", self._redis.lrange(key, start, end))
        return cast("list[str]", values)

    async def rpush(self, key: str, *values: str) -> int:
        return int(await cast("Awaitable[int]", self._redis.rpush(key, *values)))

    async def expire(self, key: str, seconds: int) -> bool:
        return bool(await cast("Awaitable[bool]", self._redis.expire(key, seconds)))

    async def llen(self, key: str) -> int:
        return int(await cast("Awaitable[int]", self._redis.llen(key)))

    async def delete(self, *keys: str) -> int:
        return int(await cast("Awaitable[int]", self._redis.delete(*keys)))

    async def aclose(self) -> None:
        await self._pool.aclose()
