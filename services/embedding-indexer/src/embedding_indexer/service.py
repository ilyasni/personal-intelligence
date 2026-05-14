# ruff: noqa: TC001
from __future__ import annotations

import re
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient, models

from embedding_indexer.settings import settings
from pil_contracts import EmbeddingJob
from pil_observability import get_logger
from pil_storage import RedisClient

log = get_logger("embedding-indexer.service")


class WormsoftEmbeddingClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.wormsoft_embedding_timeout_seconds, connect=10.0),
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        base = settings.wormsoft_api_base.rstrip("/")
        url = f"{base}/embedding"
        payload = {"model": model or settings.wormsoft_embedding_model, "input": text}
        response = await self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.wormsoft_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        vector = _extract_embedding_vector(data)
        if not vector:
            raise RuntimeError("wormsoft_embedding_response_missing_vector")
        return vector


def _extract_embedding_vector(payload: Any) -> list[float]:
    if isinstance(payload, dict):
        direct = payload.get("embedding")
        if isinstance(direct, list):
            return [float(item) for item in direct]
        data = payload.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                return [float(item) for item in first["embedding"]]
    raise RuntimeError("unsupported_embedding_payload")


def _collection_name(alias_name: str, model_name: str, dimension: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", model_name.casefold()).strip("-")
    return f"{alias_name}_{slug}_{dimension}_v1"


async def ensure_collection(
    client: AsyncQdrantClient,
    *,
    alias_name: str,
    model_name: str,
    dimension: int,
) -> str:
    collection_name = _collection_name(alias_name, model_name, dimension)
    if not await client.collection_exists(collection_name):
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )

    aliases = await client.get_aliases()
    existing_alias = next((item for item in aliases.aliases if item.alias_name == alias_name), None)
    if existing_alias is None:
        await client.update_collection_aliases(
            change_aliases_operations=[
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=collection_name,
                        alias_name=alias_name,
                    )
                )
            ]
        )
    elif existing_alias.collection_name != collection_name:
        await client.update_collection_aliases(
            change_aliases_operations=[
                models.DeleteAliasOperation(
                    delete_alias=models.DeleteAlias(alias_name=alias_name)
                ),
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=collection_name,
                        alias_name=alias_name,
                    )
                ),
            ]
        )
    return collection_name


async def _ensure_groups(redis: RedisClient) -> None:
    with suppress(Exception):
        await redis.r.xgroup_create(settings.stream_embedding, settings.consumer_group, id="$", mkstream=True)


def _payload(job: EmbeddingJob) -> dict[str, Any]:
    return {
        "owner_id": "self",
        "chat_id": str(job.tg_chat_id),
        "person_ids": job.person_ids,
        "kind": "analysis_window",
        "topic_tags": job.topic_tags,
        "ts_from": datetime.now(UTC).isoformat(),
        "ts_to": datetime.now(UTC).isoformat(),
        "embedding_profile": f"{job.profile_provider}:{job.profile_model}",
        "schema_version": job.schema_version,
        "analysis_window_id": job.analysis_window_id,
        "source_window_id": job.source_window_id,
        "narrative_text": job.narrative_text,
    }


async def run(
    redis: RedisClient,
    qdrant: AsyncQdrantClient,
    embedder: WormsoftEmbeddingClient,
) -> None:
    await _ensure_groups(redis)
    probe_vector = await embedder.embed("PIL embedding capability probe.")
    dimension = len(probe_vector)
    collection_name = await ensure_collection(
        qdrant,
        alias_name=settings.qdrant_alias_name,
        model_name=settings.wormsoft_embedding_model,
        dimension=dimension,
    )
    log.info(
        "embedding_indexer_ready",
        alias_name=settings.qdrant_alias_name,
        collection_name=collection_name,
        dimension=dimension,
    )

    while True:
        try:
            entries = await redis.xread_group(
                group=settings.consumer_group,
                consumer=settings.consumer_name,
                streams={settings.stream_embedding: ">"},
                count=settings.embedding_batch_size,
                block=5000,
            )
        except Exception as exc:
            log.error("xreadgroup_error", error=str(exc))
            continue

        if not entries:
            continue

        for stream, messages in entries:
            for msg_id, fields in messages:
                try:
                    job = EmbeddingJob.model_validate_json(str(fields.get("data", "{}")))
                    vector = await embedder.embed(job.narrative_text, model=job.profile_model)
                    await qdrant.upsert(
                        collection_name=settings.qdrant_alias_name,
                        wait=True,
                        points=[
                            models.PointStruct(
                                id=job.analysis_window_id,
                                vector=vector,
                                payload=_payload(job),
                            )
                        ],
                    )
                    log.info(
                        "embedding_upserted",
                        analysis_window_id=job.analysis_window_id,
                        tg_chat_id=job.tg_chat_id,
                        vector_dim=len(vector),
                    )
                except Exception as exc:
                    log.error("embedding_error", stream=stream, msg_id=msg_id, error=str(exc))
                finally:
                    await redis.xack(stream, settings.consumer_group, msg_id)
