from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"

    consumer_group: str = "task-extractor"
    consumer_name: str = "task-extractor-0"
    stream_message: str = "events.telegram.message"
    stream_message_edited: str = "events.telegram.message_edited"
    stream_message_deleted: str = "events.telegram.message_deleted"
    task_batch_size: int = 16

    task_rules_path: str = ""
    task_llm_mode: str = "local"
    task_min_confidence: float = 0.4
    task_dedup_window_hours: int = 12

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
