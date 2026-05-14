from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"

    maintenance_interval_hours: int = 24
    partition_months_ahead: int = 3
    processed_event_retention_days: int = 30
    startup_run: bool = True

    scheduler_timezone: str = "UTC"
    scheduler_jitter_seconds: int = 300
    scheduler_misfire_grace_seconds: int = 3600
    scheduler_max_instances: int = 1

    advisory_lock_key: int = 42042
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
