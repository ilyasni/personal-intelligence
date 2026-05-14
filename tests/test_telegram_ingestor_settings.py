import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "telegram-ingestor" / "src"))


def test_settings_allow_polling_without_webhook(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.delenv("WEBHOOK_BASE_URL", raising=False)
    monkeypatch.delenv("WEBHOOK_PATH", raising=False)

    module = importlib.import_module("telegram_ingestor.settings")
    settings = module.Settings()

    assert settings.webhook_base_url == ""
    assert settings.webhook_url == ""
