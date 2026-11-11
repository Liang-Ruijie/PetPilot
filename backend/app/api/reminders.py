from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_owner_id
from app.models import Reminder
from app.services.reminder_intent import parse_due_time
from app.services.repository import Repository, get_repo

router = APIRouter()


def _local(dt):
    """把时间转回本地时区（容器 TZ=Asia/Shanghai），统一显示与比较口径。"""
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone().replace(tzinfo=None)  # 转本地时区（北京 +8）+ 去时区
    return dt


def _to_out(r: Reminder, pet_names: dict, now: datetime) -> dict:
    due = _local(r.due_at)
    now = _local(now)
    return {
        "id": r.id,
        "pet_name": pet_names.get(r.pet_id, "") if r.pet_id else None,
        "quote": r.quote,
        "due_at": due.strftime("%Y-%m-%d %H:%M") if due else None,
        "status": r.status,
        "is_due": bool(due and due <= now and r.status == "pending"),
    }


@router.get("/reminders")
def list_reminders(
    repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)
):
    now = datetime.now()
    pet_names = {p.id: p.name for p in repo.list_pets()}
    rs = repo.list_reminders()
    return {"reminders": [_to_out(r, pet_names, now) for r in rs]}


def _transition(reminder_id: int, new_status: str, repo: Repository):
    r = repo.get_reminder(reminder_id)
    if not r:
        raise HTTPException(
            404, detail={"error": {"code": "REMINDER_NOT_FOUND", "message": "提醒不存在"}}
        )
    r.status = new_status
    repo.commit()
    return {"id": r.id, "status": r.status}


@router.post("/reminders/{reminder_id}/complete")
def complete(reminder_id: int, repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)):
    return _transition(reminder_id, "done", repo)


@router.post("/reminders/{reminder_id}/cancel")
def cancel(reminder_id: int, repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)):
    return _transition(reminder_id, "cancelled", repo)


@router.post("/reminders/{reminder_id}/pause")
def pause(reminder_id: int, repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)):
    return _transition(reminder_id, "paused", repo)


@router.post("/reminders/{reminder_id}/resume")
def resume(reminder_id: int, repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)):
    return _transition(reminder_id, "pending", repo)


class ReminderUpdate(BaseModel):
    due_at: str | None = None
    pet_id: int | None = None


@router.post("/reminders/{reminder_id}/update")
def update(reminder_id: int, body: ReminderUpdate, repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)):
    r = repo.get_reminder(reminder_id)
    if not r:
        raise HTTPException(
            404, detail={"error": {"code": "REMINDER_NOT_FOUND", "message": "提醒不存在"}}
        )
    if body.due_at:
        due = parse_due_time(body.due_at)
        if due is None:
            try:
                due = datetime.strptime(body.due_at, "%Y-%m-%d %H:%M")
            except ValueError:
                due = None
        if due is None:
            raise HTTPException(
                422, detail={"error": {"code": "TIME_PARSE_FAILED", "message": "无法解析时间，请用「明天上午九点」或「YYYY-MM-DD HH:MM」"}}
            )
        r.due_at = due
    if body.pet_id is not None:
        if repo.get_pet(body.pet_id) is None:
            raise HTTPException(
                404, detail={"error": {"code": "PET_NOT_FOUND", "message": "猫不存在"}}
            )
        r.pet_id = body.pet_id
    repo.commit()
    return {"id": r.id, "pet_id": r.pet_id, "due_at": r.due_at.strftime("%Y-%m-%d %H:%M") if r.due_at else None, "status": r.status}
