from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    postgres_dsn: str = "postgresql://pil:pil@localhost:5432/pil"

    consumer_group: str = "ai-orchestrator"
    consumer_name: str = "ai-orchestrator-0"
    stream_message: str = "events.telegram.message"
    stream_reprocess: str = "events.ai.reprocess_window"
    analysis_batch_size: int = 8

    window_strategy: str = "hybrid"
    analysis_window_size: int = 20
    analysis_time_window_minutes: int = 60

    analysis_llm_mode: str = "hybrid"
    analysis_max_tokens_out: int = 900
    analysis_output_language: str = "ru"

    wormsoft_api_base: str = "https://ai.wormsoft.ru/api/gpt"
    wormsoft_api_key: str = ""
    wormsoft_model_default: str = "wormsoft/agent/medium"
    wormsoft_max_simultaneous_requests: int = 1
    wormsoft_min_request_interval_ms: int = 250
    wormsoft_max_retries: int = 2

    polza_api_base: str = "https://polza.ai/api/v1"
    polza_api_key: str = ""
    polza_model_default: str = "deepseek/deepseek-v3.2"
    polza_max_simultaneous_requests: int = 1
    polza_min_request_interval_ms: int = 250
    polza_max_retries: int = 2

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
