from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8090
    log_level: str = "INFO"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_alias_name: str = "pil_memory_active"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    s3_endpoint_url: str = "https://s3.cloud.ru"
    s3_bucket_raw: str = "pil-raw"
    s3_bucket_media: str = "pil-raw-media"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "ru-central-1"

    wormsoft_api_base: str = "https://ai.wormsoft.ru/api/gpt"
    wormsoft_api_key: str = ""
    wormsoft_model_default: str = "wormsoft/agent/medium"
    wormsoft_max_simultaneous_requests: int = 1
    wormsoft_min_request_interval_ms: int = 250
    wormsoft_max_retries: int = 2

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
