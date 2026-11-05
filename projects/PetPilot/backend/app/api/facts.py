from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Fact, HeldSegment, Pet

router = APIRouter()


class ResolveHeld(BaseModel):
    pet_id: int


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
    helds = (
        db.query(HeldSegment)
        .filter(HeldSegment.status == "pending")
        .order_by(HeldSegment.id.desc())
        .all()
    )
    return {
        "held_segments": [
            {
                "id": h.id,
                "quote": h.quote,
                "reason": h.reason,
                "topic": h.topic,
                "value": h.value,
                "unit": h.unit,
            }
            for h in helds
        ]
    }


@router.post("/held/{held_id}/resolve")
def resolve_held(
    held_id: int,
    body: ResolveHeld,
    db: Session = Depends(get_db),
    sess=Depends(get_current_session),
):
    h = db.query(HeldSegment).filter(
        HeldSegment.id == held_id, HeldSegment.status == "pending"
    ).first()
    if not h:
        raise HTTPException(
            404, detail={"error": {"code": "HELD_NOT_FOUND", "message": "挂起片段不存在"}}
        )
    if not db.query(Pet).filter(Pet.id == body.pet_id).first():
        raise HTTPException(
            404, detail={"error": {"code": "PET_NOT_FOUND", "message": "猫不存在"}}
        )
    fact = Fact(
        pet_id=body.pet_id,
        topic=h.topic,
        value=h.value,
        unit=h.unit,
        quantity_scope=h.quantity_scope,
        historical_current=h.historical_current,
        occurred_at=h.occurred_at,
        polarity=h.polarity,
        change_kind="new",
        source_message_id=h.message_id,
        quote=h.quote,
        version=1,
    )
    db.add(fact)
    h.status = "resolved"
    h.resolved_pet_id = body.pet_id
    db.commit()
    return {"id": fact.id, "pet_id": fact.pet_id}
