from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Bot token from @BotFather (Business Mode must be enabled)
    bot_token: str

    # Webhook
    webhook_base_url: str = ""     # optional in polling mode; e.g. https://pil.example.com
    webhook_path: str = "/tg/webhook"
    webhook_secret: str = ""       # X-Telegram-Bot-Api-Secret-Token

    # Redis
    redis_url: str = "redis://redis:6379/0"
    redis_password: str = ""

    # S3 cloud.ru
    s3_endpoint_url: str = "https://s3.cloud.ru"
    s3_bucket_raw: str = "pil-raw"
    s3_bucket_media: str = "pil-raw-media"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "ru-central-1"

    # Postgres
    postgres_dsn: str = "postgresql+asyncpg://pil:pil@postgres:5432/pil"

    # Proxy for Telegram API (e.g. http://xray:8080 или socks5://xray:10808 — иногда стабильнее CONNECT)
    tg_proxy_url: str = ""
    # Таймаут HTTP к Bot API (aiogram BaseSession); через Reality+CONNECT может быть >60 с
    tg_api_timeout_seconds: float = 120.0

    # Service
    log_level: str = "INFO"
    port: int = 8080

    @property
    def webhook_url(self) -> str:
        if not self.webhook_base_url:
            return ""
        return f"{self.webhook_base_url}{self.webhook_path}"


settings = Settings()
