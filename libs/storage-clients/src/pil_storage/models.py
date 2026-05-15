"""SQLAlchemy ORM models — source of truth for Postgres schema."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# DateTime(timezone=True) → TIMESTAMPTZ в PostgreSQL
TZ = DateTime(timezone=True)


def _uuid4() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Connection(Base):
    """Привязка Telegram-аккаунта/бота к инсталляции."""

    __tablename__ = "connection"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger)
    display_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("kind IN ('telethon_userbot','business_bot')", name="ck_connection_kind"),
        CheckConstraint("status IN ('connected','disconnected','error')", name="ck_connection_status"),
    )


class Chat(Base):
    """Чат (диалог или группа). Allowlist — is_allowed."""

    __tablename__ = "chat"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    member_count: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now, onupdate=_now)

    memberships: Mapped[list["ChatMembership"]] = relationship(back_populates="chat")

    __table_args__ = (
        CheckConstraint("kind IN ('private','group','supergroup','channel')", name="ck_chat_kind"),
        Index("idx_chat_is_allowed", "is_allowed", postgresql_where="is_allowed = TRUE"),
    )


class Person(Base):
    """Профиль контакта."""

    __tablename__ = "person"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bio: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    organizations: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    manual_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    communication_style: Mapped[str | None] = mapped_column(Text)
    trust_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.5)
    last_interaction_at: Mapped[datetime | None] = mapped_column(TZ)
    notes: Mapped[str | None] = mapped_column(Text)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now, onupdate=_now)

    memberships: Mapped[list["ChatMembership"]] = relationship(back_populates="person")

    __table_args__ = (
        CheckConstraint("trust_score BETWEEN 0 AND 1", name="ck_person_trust_score"),
        Index("idx_person_username", "username"),
        Index("idx_person_last_interaction", "last_interaction_at"),
        Index("idx_person_topics_gin", "topics", postgresql_using="gin"),
        Index("idx_person_organizations_gin", "organizations", postgresql_using="gin"),
        Index("idx_person_manual_tags_gin", "manual_tags", postgresql_using="gin"),
    )


class ChatMembership(Base):
    """Кто в каком чате."""

    __tablename__ = "chat_membership"

    chat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now)
    left_at: Mapped[datetime | None] = mapped_column(TZ)
    role: Mapped[str | None] = mapped_column(Text)

    chat: Mapped["Chat"] = relationship(back_populates="memberships")
    person: Mapped["Person"] = relationship(back_populates="memberships")


class ApiKey(Base):
    """Ключи для внешних MCP-клиентов."""

    __tablename__ = "api_key"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(TZ)


class Setting(Base):
    """KV-настройки инстанса."""

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, default=_now, onupdate=_now)
