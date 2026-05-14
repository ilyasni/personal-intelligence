from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"

    entity_mode: str = "local"
    entity_min_confidence: float = 0.6
    entity_batch_size: int = 16

    consumer_group: str = "entity-extractor"
    consumer_name: str = "entity-extractor-0"
    stream_in: str = "events.telegram.message"

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
