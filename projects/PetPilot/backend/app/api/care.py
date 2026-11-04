from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import CareSummary, Pet

router = APIRouter()

_SIMULATED_REPLY = (
    "【模拟医院回复】感谢您整理的资料，我们已收到，会尽快安排查看。"
    "（本回复为演示用模拟，非真实医院发送，不代表真实接诊或预约。）"
)


@router.get("/care-summaries")
def list_summaries(
    db: Session = Depends(get_db), sess=Depends(get_current_session)
):
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    items = db.query(CareSummary).order_by(CareSummary.id.desc()).all()
    return {
        "care_summaries": [
            {
                "id": c.id,
                "pet_name": pet_names.get(c.pet_id, ""),
                "title": c.title,
                "summary": c.summary,
                "stale": c.stale,
            }
            for c in items
        ]
    }


@router.post("/care-summaries/{summary_id}/simulate-reply")
def simulate_reply(
    summary_id: int,
    db: Session = Depends(get_db),
    sess=Depends(get_current_session),
):
    cs = db.query(CareSummary).filter(CareSummary.id == summary_id).first()
    if not cs:
        raise HTTPException(
            404, detail={"error": {"code": "CARE_NOT_FOUND", "message": "摘要不存在"}}
        )
    return {"reply": _SIMULATED_REPLY, "is_simulated": True}
