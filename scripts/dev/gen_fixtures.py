from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_DNS, uuid5

ROOT = Path(__file__).resolve().parents[2]

import sys

sys.path.insert(0, str(ROOT / "libs" / "contracts" / "src"))

from pil_contracts import TelegramMessageEvent


DEFAULT_OUTPUT_DIR = ROOT / "tests" / "fixtures"
DEFAULT_SEED = 20260514
EMBEDDING_DIMENSION = 8


@dataclass(frozen=True)
class PersonBlueprint:
    slug: str
    tg_user_id: int
    username: str
    display_name: str
    is_owner: bool
    organizations: list[str]
    topics: list[str]
    notes: str


@dataclass(frozen=True)
class ChatBlueprint:
    slug: str
    tg_chat_id: int
    kind: str
    title: str
    participant_slugs: list[str]
    is_allowed: bool = True


PERSONS = [
    PersonBlueprint(
        slug="owner",
        tg_user_id=700000001,
        username="ilya_owner",
        display_name="Ilya Nikitin",
        is_owner=True,
        organizations=["frontier-intelligence", "wormsoft-labs"],
        topics=["personal-intelligence", "ai-architecture", "product-strategy"],
        notes="Owner profile used for deterministic PIL demo data.",
    ),
    PersonBlueprint(
        slug="anna",
        tg_user_id=700000101,
        username="annapm",
        display_name="Anna Petrova",
        is_owner=False,
        organizations=["north-star-product"],
        topics=["roadmap", "customer-research", "analytics"],
        notes="Product manager counterpart for task-heavy chats.",
    ),
    PersonBlueprint(
        slug="maksim",
        tg_user_id=700000102,
        username="maksdev",
        display_name="Maksim Volkov",
        is_owner=False,
        organizations=["north-star-product"],
        topics=["backend", "postgres", "redis-streams"],
        notes="Engineering lead for group conversation fixtures.",
    ),
    PersonBlueprint(
        slug="sergey",
        tg_user_id=700000103,
        username="sergey_sales",
        display_name="Sergey Kim",
        is_owner=False,
        organizations=["east-bridge-consulting"],
        topics=["contracts", "pricing", "follow-up"],
        notes="Sales-style contact used for promises and due dates.",
    ),
    PersonBlueprint(
        slug="elena",
        tg_user_id=700000104,
        username="elenadata",
        display_name="Elena Sokolova",
        is_owner=False,
        organizations=["insight-lab"],
        topics=["embeddings", "qdrant", "evaluation"],
        notes="Data/ML profile for embeddings and analytics fixtures.",
    ),
]

CHATS = [
    ChatBlueprint(
        slug="anna-private",
        tg_chat_id=810000001,
        kind="private",
        title="Anna Petrova",
        participant_slugs=["owner", "anna"],
    ),
    ChatBlueprint(
        slug="product-sync",
        tg_chat_id=810000002,
        kind="group",
        title="Product Sync",
        participant_slugs=["owner", "anna", "maksim", "elena"],
    ),
    ChatBlueprint(
        slug="sergey-private",
        tg_chat_id=810000003,
        kind="private",
        title="Sergey Kim",
        participant_slugs=["owner", "sergey"],
    ),
]

MESSAGE_SCENARIOS: dict[str, list[tuple[str, str]]] = {
    "anna-private": [
        ("anna", "I put the roadmap notes in Notion. Please review the Q2 priorities today."),
        ("owner", "Got it, I will review the roadmap and send comments before 18:00."),
        ("anna", "Also check the analytics screenshot in https://example.com/q2-metrics."),
        ("owner", "Will do. I will summarize the metrics and update the launch checklist."),
    ],
    "product-sync": [
        ("maksim", "Redis backlog is stable, but we still need a cleanup plan for old consumer groups."),
        ("elena", "Qdrant alias switch looked good. I can prepare an evaluation note for embeddings tomorrow."),
        ("owner", "Please prepare the note and include wormsoft versus polza trade-offs."),
        ("anna", "I need a concise summary for stakeholders by Friday morning."),
        ("owner", "I will send the stakeholder summary and tag the open tasks after lunch."),
    ],
    "sergey-private": [
        ("sergey", "Can you send the updated contract draft this week?"),
        ("owner", "Yes, I will send the contract draft tomorrow morning."),
        ("sergey", "Perfect, then I will confirm pricing on my side."),
    ],
}


def stable_uuid(label: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"pil-fixture:{label}"))


def _embedding_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vector: list[float] = []
    for index in range(EMBEDDING_DIMENSION):
        chunk = digest[index * 4 : (index + 1) * 4]
        value = int.from_bytes(chunk, "big") / 0xFFFFFFFF
        vector.append(round((value * 2.0) - 1.0, 6))
    return vector


def build_persons() -> list[dict[str, Any]]:
    return [
        {
            "id": stable_uuid(f"person:{person.slug}"),
            "slug": person.slug,
            "tg_user_id": person.tg_user_id,
            "username": person.username,
            "display_name": person.display_name,
            "is_owner": person.is_owner,
            "organizations": person.organizations,
            "topics": person.topics,
            "notes": person.notes,
        }
        for person in PERSONS
    ]


def build_chats() -> list[dict[str, Any]]:
    people_by_slug = {person.slug: person for person in PERSONS}
    chats: list[dict[str, Any]] = []
    for chat in CHATS:
        chats.append(
            {
                "id": stable_uuid(f"chat:{chat.slug}"),
                "slug": chat.slug,
                "tg_chat_id": chat.tg_chat_id,
                "kind": chat.kind,
                "title": chat.title,
                "is_allowed": chat.is_allowed,
                "participants": [
                    {
                        "person_slug": slug,
                        "tg_user_id": people_by_slug[slug].tg_user_id,
                        "display_name": people_by_slug[slug].display_name,
                    }
                    for slug in chat.participant_slugs
                ],
            }
        )
    return chats


def build_message_events(seed: int) -> list[TelegramMessageEvent]:
    rng = random.Random(seed)
    people_by_slug = {person.slug: person for person in PERSONS}
    chats_by_slug = {chat.slug: chat for chat in CHATS}

    events: list[TelegramMessageEvent] = []
    base_time = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)
    message_id = 1000

    for chat_index, chat in enumerate(CHATS):
        current_time = base_time + timedelta(hours=chat_index * 3)
        previous_message_id: int | None = None
        for turn_index, (speaker_slug, text) in enumerate(MESSAGE_SCENARIOS[chat.slug]):
            person = people_by_slug[speaker_slug]
            reply_to = previous_message_id if turn_index > 0 and turn_index % 2 == 1 else None
            message_id += 1
            events.append(
                TelegramMessageEvent(
                    event_id=f"fixture-{chat.slug}-{message_id}",
                    occurred_at=current_time,
                    trace_id=f"fixture-trace-{chat.slug}",
                    tg_chat_id=chat.tg_chat_id,
                    tg_message_id=message_id,
                    tg_sender_id=person.tg_user_id,
                    tg_sender_username=person.username,
                    tg_sender_name=person.display_name,
                    chat_title=chat.title,
                    chat_type=chat.kind,
                    text=text,
                    reply_to_message_id=reply_to,
                    is_forwarded=turn_index == 2 and chat.kind == "group",
                    tg_date=current_time,
                    raw_s3_key=f"raw/2026/05/14/{chat.tg_chat_id}/{message_id}.json",
                )
            )
            previous_message_id = message_id
            current_time += timedelta(minutes=5 + rng.randint(0, 10))

    return events


def build_summary_gold(events: list[TelegramMessageEvent]) -> list[dict[str, Any]]:
    grouped: dict[int, list[TelegramMessageEvent]] = {}
    for event in events:
        grouped.setdefault(event.tg_chat_id, []).append(event)

    output: list[dict[str, Any]] = []
    for chat in CHATS:
        chat_events = grouped[chat.tg_chat_id]
        text_blob = " ".join(event.text or "" for event in chat_events)
        topics = []
        for candidate in ("roadmap", "analytics", "contracts", "embeddings", "tasks", "redis"):
            if candidate in text_blob.lower():
                topics.append(candidate)
        output.append(
            {
                "chat_slug": chat.slug,
                "tg_chat_id": chat.tg_chat_id,
                "message_ids": [event.tg_message_id for event in chat_events],
                "summary": _summary_for_chat(chat.slug),
                "topics": topics,
            }
        )
    return output


def _summary_for_chat(chat_slug: str) -> str:
    if chat_slug == "anna-private":
        return "Anna asks for roadmap and analytics review; the owner promises comments and a checklist update today."
    if chat_slug == "product-sync":
        return "The group discusses Redis cleanup, embeddings evaluation, and a stakeholder summary due by Friday."
    return "Sergey requests an updated contract draft, and the owner commits to sending it tomorrow morning."


def build_embeddings(events: list[TelegramMessageEvent]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for chat in CHATS:
        chat_events = [event for event in events if event.tg_chat_id == chat.tg_chat_id]
        narrative = " ".join((event.text or "") for event in chat_events)
        records.append(
            {
                "chunk_id": stable_uuid(f"embedding:{chat.slug}"),
                "chat_slug": chat.slug,
                "tg_chat_id": chat.tg_chat_id,
                "text": narrative,
                "vector": _embedding_vector(narrative),
                "profile_provider": "wormsoft",
                "profile_model": "qwen/qwen3-embedding:8b",
                "profile_alias": "pil_memory_active",
            }
        )
    return records


def build_sql_seed(persons: list[dict[str, Any]], chats: list[dict[str, Any]]) -> str:
    lines = ["-- Deterministic fixture seed generated by scripts/dev/gen_fixtures.py", "BEGIN;"]

    for person in persons:
        organizations = "{" + ",".join(person["organizations"]) + "}"
        topics = "{" + ",".join(person["topics"]) + "}"
        notes = person["notes"].replace("'", "''")
        lines.append(
            "INSERT INTO person (id, tg_user_id, username, display_name, is_owner, organizations, topics, notes) "
            f"VALUES ('{person['id']}', {person['tg_user_id']}, '{person['username']}', '{person['display_name']}', "
            f"{str(person['is_owner']).upper()}, '{organizations}', '{topics}', '{notes}') "
            "ON CONFLICT (tg_user_id) DO NOTHING;"
        )

    for chat in chats:
        title = chat["title"].replace("'", "''")
        lines.append(
            "INSERT INTO chat (id, tg_chat_id, kind, title, is_allowed, metadata) "
            f"VALUES ('{chat['id']}', {chat['tg_chat_id']}, '{chat['kind']}', '{title}', "
            f"{str(chat['is_allowed']).upper()}, '{{}}'::jsonb) "
            "ON CONFLICT (tg_chat_id) DO NOTHING;"
        )
        for member in chat["participants"]:
            person_id = stable_uuid(f"person:{member['person_slug']}")
            lines.append(
                "INSERT INTO chat_membership (chat_id, person_id) "
                f"VALUES ('{chat['id']}', '{person_id}') ON CONFLICT DO NOTHING;"
            )

    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(item, ensure_ascii=False) for item in items) + "\n"
    path.write_text(content, encoding="utf-8")


def generate_fixture_bundle(output_dir: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    persons = build_persons()
    chats = build_chats()
    events = build_message_events(seed)
    summaries = build_summary_gold(events)
    embeddings = build_embeddings(events)

    write_json(output_dir / "persons" / "seed_persons.json", persons)
    write_json(output_dir / "chats" / "seed_chats.json", chats)
    write_jsonl(
        output_dir / "events" / "telegram_messages.jsonl",
        [event.model_dump(mode="json") for event in events],
    )
    write_json(output_dir / "telegram_updates.json", [event.model_dump(mode="json") for event in events])
    write_json(output_dir / "messages_for_entities.json", [event.model_dump(mode="json") for event in events])
    write_json(output_dir / "summaries_gold.json", summaries)
    write_json(output_dir / "embeddings.json", embeddings)
    sql_path = output_dir / "sql" / "seed_reference.sql"
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text(build_sql_seed(persons, chats), encoding="utf-8")

    manifest = {
        "seed": seed,
        "generator_version": 1,
        "persons": len(persons),
        "chats": len(chats),
        "messages": len(events),
        "embeddings": len(embeddings),
        "files": [
            "persons/seed_persons.json",
            "chats/seed_chats.json",
            "events/telegram_messages.jsonl",
            "telegram_updates.json",
            "messages_for_entities.json",
            "summaries_gold.json",
            "embeddings.json",
            "sql/seed_reference.sql",
        ],
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic PIL seed fixtures.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where fixture files should be written.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Deterministic seed for generated fixture content.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_fixture_bundle(args.output_dir, args.seed)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
