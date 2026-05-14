from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"

    consumer_group: str = "persona-builder"
    consumer_name: str = "persona-builder-0"
    stream_in: str = "events.processing.entity_found"

    persona_batch_size: int = 20
    persona_topics_window_days: int = 30
    persona_max_topics: int = 20
    persona_max_organizations: int = 10

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
