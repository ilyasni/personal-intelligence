from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"

    consumer_group: str = "memory-projector"
    consumer_name: str = "memory-projector-0"
    stream_projection: str = "events.ai.projection_command"
    projection_batch_size: int = 8

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    s3_endpoint_url: str = "https://s3.cloud.ru"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "ru-central-1"
    s3_bucket_raw: str = "pil-raw"
    s3_bucket_media: str = "pil-raw-media"

    embedding_provider: str = "wormsoft"
    embedding_model: str = "qwen/qwen3-embedding:8b"
    embedding_alias: str = "pil_memory_active"

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
