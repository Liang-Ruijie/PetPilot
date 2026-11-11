"""测试空间（demo）的登录重置与预置测试数据。"""
from datetime import datetime, timedelta

from app.config import settings


def _repo_for(owner_id: str):
    from app.db import SessionLocal
    from app.services.repository import SqlRepository
    if settings.data_backend == "cloudbase_rest":
        from app.services.rest_repository import get_rest_repo
        return get_rest_repo(settings, owner_id)
    return SqlRepository(SessionLocal(), owner_id=owner_id)


def seed_demo(repo) -> None:
    """写入预置测试数据：两只猫 + 三条记录 + 一个提醒。"""
    mingyue = repo.create_pet("明月")
    beita = repo.create_pet("贝塔")
    repo.flush()
    repo.create_fact(pet_id=mingyue.id, topic="进食", value=20, unit="克",
                     change_kind="new", source_message_id=None, quote="明月昨天吃了20克", version=1)
    repo.create_fact(pet_id=mingyue.id, topic="进食", value=23, unit="克",
                     change_kind="new", source_message_id=None, quote="明月今天吃了23克", version=1)
    repo.create_fact(pet_id=beita.id, topic="状态", polarity="negative",
                     change_kind="new", source_message_id=None, quote="贝塔今天便便偏软", version=1)
    due = (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    repo.create_reminder(pet_id=mingyue.id, quote="明天上午九点提醒我给明月称重", due_at=due, status="pending")
    repo.commit()


def reset_demo() -> None:
    """demo 空间每次登录：清空 + 写入预置测试数据。"""
    owner = settings.demo_label
    repo = _repo_for(owner)
    repo.clear_owner(owner)
    seed_demo(repo)
