from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Pet, Reminder

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
