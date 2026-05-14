from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"

    s3_endpoint_url: str = "https://s3.cloud.ru"
    s3_bucket_raw: str = "pil-raw"
    s3_bucket_media: str = "pil-raw-media"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "ru-central-1"

    consumer_group: str = "chat-summarizer"
    consumer_name: str = "chat-summarizer-0"
    stream_message: str = "events.telegram.message"
    stream_message_edited: str = "events.telegram.message_edited"
    summarizer_batch_size: int = 16

    summarizer_strategy: str = "by_count"
    summarizer_window_size: int = 50
    summarizer_time_window_minutes: int = 60
    summarizer_max_summary_chars: int = 350
    summarizer_max_tasks: int = 5
    summarizer_llm_mode: str = "local"
    summarizer_max_tokens_out: int = 400

    wormsoft_api_base: str = "https://ai.wormsoft.ru/api/gpt"
    wormsoft_api_key: str = ""
    wormsoft_model_default: str = "wormsoft/agent/medium"
    wormsoft_max_simultaneous_requests: int = 1
    wormsoft_min_request_interval_ms: int = 250
    wormsoft_max_retries: int = 2

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
