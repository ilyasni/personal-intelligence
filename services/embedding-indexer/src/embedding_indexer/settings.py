from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    consumer_group: str = "embedding-indexer"
    consumer_name: str = "embedding-indexer-0"
    stream_embedding: str = "events.ai.embedding_requested"
    embedding_batch_size: int = 8

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_alias_name: str = "pil_memory_active"
    qdrant_distance: str = "Cosine"

    wormsoft_api_base: str = "https://ai.wormsoft.ru/api/gpt"
    wormsoft_api_key: str = ""
    wormsoft_embedding_model: str = "qwen/qwen3-embedding:8b"
    wormsoft_embedding_timeout_seconds: float = 60.0

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
