from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Fact, HeldSegment, Pet

router = APIRouter()


@router.get("/facts")
def list_facts(
    pet_id: int | None = None,
    db: Session = Depends(get_db),
    sess=Depends(get_current_session),
):
    q = db.query(Fact)
    if pet_id is not None:
        if not db.query(Pet).filter(Pet.id == pet_id).first():
            raise HTTPException(
                404, detail={"error": {"code": "PET_NOT_FOUND", "message": "猫不存在"}}
            )
        q = q.filter(Fact.pet_id == pet_id)
    facts = q.order_by(Fact.id.desc()).all()
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    return {
        "facts": [
            {
                "id": f.id,
                "pet_id": f.pet_id,
                "pet_name": pet_names.get(f.pet_id, ""),
                "topic": f.topic,
                "value": f.value,
                "unit": f.unit,
                "quote": f.quote,
                "version": f.version,
            }
            for f in facts
        ]
    }


@router.get("/held")
def list_held(
    db: Session = Depends(get_db), sess=Depends(get_current_session)
):
    helds = db.query(HeldSegment).order_by(HeldSegment.id.desc()).all()
    return {
        "held_segments": [
            {"id": h.id, "quote": h.quote, "reason": h.reason} for h in helds
        ]
    }
