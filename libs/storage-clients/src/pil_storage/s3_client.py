from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiobotocore.session
from botocore.config import Config as BotoConfig


@dataclass
class S3Client:
    """S3-compatible client for cloud.ru and other boto3-compatible stores."""

    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    region: str
    bucket_raw: str
    bucket_media: str
    addressing_style: str = "path"
    signature_version: str = "s3v4"

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key and self.bucket_raw and self.bucket_media)

    @asynccontextmanager
    async def _client(self) -> AsyncGenerator[object, None]:
        session = aiobotocore.session.get_session()
        async with session.create_client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=BotoConfig(
                signature_version=self.signature_version,
                s3={"addressing_style": self.addressing_style},
            ),
        ) as client:
            yield client

    async def put_raw(self, key: str, body: bytes, content_type: str = "application/json") -> str:
        full_key = f"raw/{key}"
        return await self.put_bucket_object(self.bucket_raw, full_key, body, content_type=content_type)

    async def put_media(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
        full_key = f"media/{key}"
        return await self.put_bucket_object(self.bucket_media, full_key, body, content_type=content_type)

    async def put_bucket_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        async with self._client() as client:
            await client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        return key

    async def get_raw(self, key: str) -> bytes:
        async with self._client() as client:
            response = await client.get_object(Bucket=self.bucket_raw, Key=key)
            return await response["Body"].read()
