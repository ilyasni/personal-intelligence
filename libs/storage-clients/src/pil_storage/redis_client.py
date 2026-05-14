from dataclasses import dataclass

import redis.asyncio as aioredis


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
        return await self._redis.xadd(stream, fields)  # type: ignore[return-value]

    async def xread_group(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int = 10,
        block: int = 5000,
    ) -> list:
        return await self._redis.xreadgroup(  # type: ignore[return-value]
            group, consumer, streams, count=count, block=block
        )

    async def xack(self, stream: str, group: str, *ids: str) -> int:
        return await self._redis.xack(stream, group, *ids)  # type: ignore[return-value]

    async def ping(self) -> bool:
        return await self._redis.ping()  # type: ignore[return-value]

    async def aclose(self) -> None:
        await self._pool.aclose()
