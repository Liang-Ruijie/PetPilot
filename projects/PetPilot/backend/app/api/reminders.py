from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Pet, Reminder
from app.services.reminder_intent import parse_due_time

router = APIRouter()


def _to_out(r: Reminder, pet_names: dict, now: datetime) -> dict:
    due = r.due_at
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
    db: Session = Depends(get_db), sess=Depends(get_current_session)
):
    now = datetime.now()
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    rs = db.query(Reminder).order_by(Reminder.id.desc()).all()
    return {"reminders": [_to_out(r, pet_names, now) for r in rs]}


def _transition(reminder_id: int, new_status: str, db: Session):
    r = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not r:
        raise HTTPException(
            404, detail={"error": {"code": "REMINDER_NOT_FOUND", "message": "提醒不存在"}}
        )
    r.status = new_status
    db.commit()
    return {"id": r.id, "status": r.status}


@router.post("/reminders/{reminder_id}/complete")
def complete(reminder_id: int, db: Session = Depends(get_db), sess=Depends(get_current_session)):
    return _transition(reminder_id, "done", db)


@router.post("/reminders/{reminder_id}/cancel")
def cancel(reminder_id: int, db: Session = Depends(get_db), sess=Depends(get_current_session)):
    return _transition(reminder_id, "cancelled", db)


@router.post("/reminders/{reminder_id}/pause")
def pause(reminder_id: int, db: Session = Depends(get_db), sess=Depends(get_current_session)):
    return _transition(reminder_id, "paused", db)


class ReminderUpdate(BaseModel):
    due_at: str | None = None
    pet_id: int | None = None


@router.post("/reminders/{reminder_id}/update")
def update(reminder_id: int, body: ReminderUpdate, db: Session = Depends(get_db), sess=Depends(get_current_session)):
    r = db.query(Reminder).filter(Reminder.id == reminder_id).first()
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
        r.pet_id = body.pet_id
    db.commit()
    return {"id": r.id, "pet_id": r.pet_id, "due_at": r.due_at.strftime("%Y-%m-%d %H:%M") if r.due_at else None, "status": r.status}
