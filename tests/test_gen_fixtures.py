import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from gen_fixtures import DEFAULT_SEED, generate_fixture_bundle


def test_generate_fixture_bundle_creates_expected_files(tmp_path: Path) -> None:
    manifest = generate_fixture_bundle(tmp_path, seed=DEFAULT_SEED)

    assert manifest["persons"] == 5
    assert manifest["chats"] == 3
    assert manifest["messages"] == 12
    assert manifest["embeddings"] == 3

    persons = json.loads((tmp_path / "persons" / "seed_persons.json").read_text(encoding="utf-8"))
    chats = json.loads((tmp_path / "chats" / "seed_chats.json").read_text(encoding="utf-8"))
    embeddings = json.loads((tmp_path / "embeddings.json").read_text(encoding="utf-8"))
    message_lines = (tmp_path / "events" / "telegram_messages.jsonl").read_text(encoding="utf-8").splitlines()

    assert persons[0]["slug"] == "owner"
    assert chats[1]["slug"] == "product-sync"
    assert len(embeddings[0]["vector"]) == 8
    assert len(message_lines) == 12


def test_generate_fixture_bundle_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"

    generate_fixture_bundle(left, seed=DEFAULT_SEED)
    generate_fixture_bundle(right, seed=DEFAULT_SEED)

    left_messages = (left / "events" / "telegram_messages.jsonl").read_text(encoding="utf-8")
    right_messages = (right / "events" / "telegram_messages.jsonl").read_text(encoding="utf-8")
    left_embeddings = (left / "embeddings.json").read_text(encoding="utf-8")
    right_embeddings = (right / "embeddings.json").read_text(encoding="utf-8")

    assert left_messages == right_messages
    assert left_embeddings == right_embeddings
