"""数据访问统一接口。所有查询都按 owner_id 过滤（权限判断在后端，多用户隔离）。

两种实现，接口相同（见 Repository）：
- SqlRepository：SQLAlchemy，本地 SQLite（默认，DATA_BACKEND=sql）
- RestRepository：腾讯云开发 PostgreSQL 的 HTTPS 网关（DATA_BACKEND=cloudbase_rest，见 rest_repository.py）

接口层通过 get_repo 依赖拿实现，不关心是哪一种。owner_id 由登录态注入（本地固定 "local"，线上为邀请码标签）。
"""
from __future__ import annotations

from typing import Any, Protocol
from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.dependencies import get_owner_id
from app.models import (
    CareSummary,
    Correction,
    Fact,
    HeldSegment,
    Message,
    Pet,
    Photo,
    Reminder,
    User,
    WeeklyReview,
)


# ---------------- 统一接口 ----------------

class Repository(Protocol):
    # pets
    def list_pets(self) -> list: ...
    def get_pet(self, pet_id: int) -> Any: ...
    def get_pet_by_name(self, name: str) -> Any: ...
    def create_pet(self, name: str) -> Any: ...

    # messages
    def create_message(self, role: str, content: str) -> Any: ...
    def list_recent_messages(self, limit: int = 20) -> list: ...
    def delete_message(self, message_id: int) -> None: ...

    # facts
    def list_facts(self, pet_id: int | None = None) -> list: ...
    def list_recent_facts(self, limit: int = 20) -> list: ...
    def create_fact(self, **kw) -> Any: ...
    def get_fact(self, fact_id: int) -> Any: ...

    # held segments
    def list_pending_held(self) -> list: ...
    def create_held(self, **kw) -> Any: ...
    def get_held(self, held_id: int) -> Any: ...
    def get_pending_held(self, held_id: int) -> Any: ...

    # corrections
    def create_correction(self, **kw) -> Any: ...

    # reminders
    def list_reminders(self) -> list: ...
    def create_reminder(self, **kw) -> Any: ...
    def get_reminder(self, reminder_id: int) -> Any: ...

    # photos
    def list_photos(self, pet_id: int | None = None) -> list: ...
    def create_photo(self, **kw) -> Any: ...
    def get_photo(self, photo_id: int) -> Any: ...

    # care summaries
    def list_care_summaries(self) -> list: ...
    def create_care_summary(self, **kw) -> Any: ...
    def get_care_summary(self, summary_id: int) -> Any: ...

    # weekly reviews
    def list_weekly_reviews(self) -> list: ...
    def create_weekly_review(self, **kw) -> Any: ...

    # user
    def touch_user(self, label: str) -> None: ...
    def clear_owner(self, owner_id: str) -> None: ...

    def commit(self) -> None: ...
    def flush(self) -> None: ...
    def refresh(self, obj: Any) -> None: ...
    def ping(self) -> None: ...


# ---------------- SQL 实现（本地） ----------------

class SqlRepository:
    def __init__(self, session: Session, owner_id: str | None = None) -> None:
        self.session = session
        self.owner_id = owner_id

    def _own(self, q, model):
        if self.owner_id is not None:
            return q.filter(model.owner_id == self.owner_id)
        return q

    # pets
    def list_pets(self) -> list[Pet]:
        q = self.session.query(Pet)
        return list(self._own(q, Pet).order_by(Pet.id).all())

    def get_pet(self, pet_id: int) -> Pet | None:
        q = self.session.query(Pet).filter(Pet.id == pet_id)
        return self._own(q, Pet).first()

    def get_pet_by_name(self, name: str) -> Pet | None:
        q = self.session.query(Pet).filter(Pet.name == name)
        return self._own(q, Pet).first()

    def create_pet(self, name: str) -> Pet:
        p = Pet(name=name)
        if self.owner_id is not None:
            p.owner_id = self.owner_id
        self.session.add(p)
        return p

    # messages
    def create_message(self, role: str, content: str) -> Message:
        m = Message(role=role, content=content)
        if self.owner_id is not None:
            m.owner_id = self.owner_id
        self.session.add(m)
        return m

    def list_recent_messages(self, limit: int = 20) -> list[Message]:
        q = self._own(self.session.query(Message), Message).order_by(Message.id.desc()).limit(limit)
        return list(q.all())

    def delete_message(self, message_id: int) -> None:
        m = self.session.get(Message, message_id)
        if m is not None:
            self.session.delete(m)
            self.session.commit()

    # facts
    def list_facts(self, pet_id: int | None = None) -> list[Fact]:
        q = self.session.query(Fact)
        if pet_id is not None:
            q = q.filter(Fact.pet_id == pet_id)
        return list(self._own(q, Fact).order_by(Fact.id.desc()).all())

    def list_recent_facts(self, limit: int = 20) -> list[Fact]:
        q = self._own(self.session.query(Fact), Fact).order_by(Fact.id.desc()).limit(limit)
        return list(q.all())

    def create_fact(self, **kw) -> Fact:
        f = Fact(**kw)
        if self.owner_id is not None:
            f.owner_id = self.owner_id
        self.session.add(f)
        return f

    def get_fact(self, fact_id: int) -> Fact | None:
        q = self.session.query(Fact).filter(Fact.id == fact_id)
        return self._own(q, Fact).first()

    # held segments
    def list_pending_held(self) -> list[HeldSegment]:
        q = self.session.query(HeldSegment).filter(HeldSegment.status == "pending")
        return list(self._own(q, HeldSegment).order_by(HeldSegment.id.desc()).all())

    def create_held(self, **kw) -> HeldSegment:
        h = HeldSegment(**kw)
        if self.owner_id is not None:
            h.owner_id = self.owner_id
        self.session.add(h)
        return h

    def get_held(self, held_id: int) -> HeldSegment | None:
        q = self.session.query(HeldSegment).filter(HeldSegment.id == held_id)
        return self._own(q, HeldSegment).first()

    def get_pending_held(self, held_id: int) -> HeldSegment | None:
        q = self.session.query(HeldSegment).filter(
            HeldSegment.id == held_id, HeldSegment.status == "pending"
        )
        return self._own(q, HeldSegment).first()

    # corrections
    def create_correction(self, **kw) -> Correction:
        c = Correction(**kw)
        if self.owner_id is not None:
            c.owner_id = self.owner_id
        self.session.add(c)
        return c

    # reminders
    def list_reminders(self) -> list[Reminder]:
        q = self.session.query(Reminder)
        return list(self._own(q, Reminder).order_by(Reminder.id.desc()).all())

    def create_reminder(self, **kw) -> Reminder:
        r = Reminder(**kw)
        if self.owner_id is not None:
            r.owner_id = self.owner_id
        self.session.add(r)
        return r

    def get_reminder(self, reminder_id: int) -> Reminder | None:
        q = self.session.query(Reminder).filter(Reminder.id == reminder_id)
        return self._own(q, Reminder).first()

    # photos
    def list_photos(self, pet_id: int | None = None) -> list[Photo]:
        q = self.session.query(Photo)
        if pet_id is not None:
            q = q.filter(Photo.pet_id == pet_id)
        return list(self._own(q, Photo).order_by(Photo.id.desc()).all())

    def create_photo(self, **kw) -> Photo:
        p = Photo(**kw)
        if self.owner_id is not None:
            p.owner_id = self.owner_id
        self.session.add(p)
        return p

    def get_photo(self, photo_id: int) -> Photo | None:
        q = self.session.query(Photo).filter(Photo.id == photo_id)
        return self._own(q, Photo).first()

    # care summaries
    def list_care_summaries(self) -> list[CareSummary]:
        q = self.session.query(CareSummary)
        return list(self._own(q, CareSummary).order_by(CareSummary.id.desc()).all())

    def create_care_summary(self, **kw) -> CareSummary:
        c = CareSummary(**kw)
        if self.owner_id is not None:
            c.owner_id = self.owner_id
        self.session.add(c)
        return c

    def get_care_summary(self, summary_id: int) -> CareSummary | None:
        q = self.session.query(CareSummary).filter(CareSummary.id == summary_id)
        return self._own(q, CareSummary).first()

    # weekly reviews
    def list_weekly_reviews(self) -> list[WeeklyReview]:
        q = self.session.query(WeeklyReview)
        return list(self._own(q, WeeklyReview).order_by(WeeklyReview.id.desc()).all())

    def create_weekly_review(self, **kw) -> WeeklyReview:
        w = WeeklyReview(**kw)
        if self.owner_id is not None:
            w.owner_id = self.owner_id
        self.session.add(w)
        return w

    # user
    def touch_user(self, label: str) -> None:
        from datetime import datetime
        u = self.session.query(User).filter(User.label == label).first()
        if u is None:
            self.session.add(User(label=label, created_at=datetime.now(), last_login_at=datetime.now()))
        else:
            u.last_login_at = datetime.now()
        self.session.commit()

    def clear_owner(self, owner_id: str) -> None:
        """清空某用户空间的所有业务数据（不删用户本身）。按外键依赖：先删子表（corrections 引用 facts），再删父表。"""
        for model in (Correction, Fact, HeldSegment, Reminder, Photo, CareSummary, WeeklyReview, Message, Pet):
            self.session.query(model).filter(model.owner_id == owner_id).delete()
        self.session.commit()

    def commit(self) -> None:
        self.session.commit()

    def flush(self) -> None:
        self.session.flush()

    def refresh(self, obj: Any) -> None:
        self.session.refresh(obj)

    def ping(self) -> None:
        self.session.execute(text("SELECT 1"))


# ---------------- 依赖 ----------------

def get_repo(owner_id: str = Depends(get_owner_id)) -> Iterator[Repository]:
    """FastAPI 依赖：按 DATA_BACKEND 返回实现；owner_id 由登录态注入（本地 "local"）。"""
    if settings.data_backend == "cloudbase_rest":
        from app.services.rest_repository import get_rest_repo
        yield get_rest_repo(settings, owner_id)
        return
    session = SessionLocal()
    try:
        yield SqlRepository(session, owner_id=owner_id)
    finally:
        session.close()
