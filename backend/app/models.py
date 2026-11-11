from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    """邀请码对应的用户（owner_id 即 label）。线上为多用户隔离，本地单用户也用同一个结构。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_login_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Session(Base):
    """本地开发期的 Bearer 会话表；上线切到 Cookie 会话后可废弃。"""

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Pet(Base):
    __tablename__ = "pets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id"), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(50))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    quantity_scope: Mapped[str | None] = mapped_column(String(20))
    historical_current: Mapped[str | None] = mapped_column(String(20))
    occurred_at: Mapped[date | None] = mapped_column(Date)
    polarity: Mapped[str | None] = mapped_column(String(20))
    change_kind: Mapped[str] = mapped_column(String(20), default="new")
    source_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class HeldSegment(Base):
    __tablename__ = "held_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(String(50), default="归属未知")
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    quantity_scope: Mapped[str | None] = mapped_column(String(20))
    historical_current: Mapped[str | None] = mapped_column(String(20))
    occurred_at: Mapped[date | None] = mapped_column(Date)
    polarity: Mapped[str | None] = mapped_column(String(20))
    resolved_pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id"), nullable=False)
    old_value: Mapped[float | None] = mapped_column(Float)
    new_value: Mapped[float | None] = mapped_column(Float)
    old_topic: Mapped[str | None] = mapped_column(String(50))
    new_topic: Mapped[str | None] = mapped_column(String(50))
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id"))
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CareSummary(Base):
    __tablename__ = "care_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pet_id: Mapped[int] = mapped_column(ForeignKey("pets.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    source_message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pet_id: Mapped[int | None] = mapped_column(ForeignKey("pets.id"))
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
