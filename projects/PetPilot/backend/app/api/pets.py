from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Fact, HeldSegment, Pet, Reminder
from app.schemas import PetCreate, PetOut
from app.services.attribution import mention_count

router = APIRouter()


@router.get("/pets")
def list_pets(
    db: Session = Depends(get_db), sess=Depends(get_current_session)
):
    pets = db.query(Pet).order_by(Pet.id).all()
    return {"pets": [{"id": p.id, "name": p.name} for p in pets]}


@router.post("/pets", response_model=PetOut, status_code=201)
def create_pet(
    body: PetCreate,
    db: Session = Depends(get_db),
    sess=Depends(get_current_session),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(
            422, detail={"error": {"code": "VALIDATION_ERROR", "message": "名字不能为空"}}
        )
    if db.query(Pet).filter(Pet.name == name).first():
        raise HTTPException(
            409, detail={"error": {"code": "PET_NAME_DUPLICATE", "message": "已有同名猫"}}
        )
    pet = Pet(name=name)
    db.add(pet)
    db.flush()

    # 补归属（R11/R12）：把之前挂起的、提到这只猫的片段自动归到它名下
    pending = db.query(HeldSegment).filter(HeldSegment.status == "pending").all()
    for h in pending:
        if mention_count(name, h.quote) >= 1:
            db.add(
                Fact(
                    pet_id=pet.id,
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
            )
            h.status = "resolved"
            h.resolved_pet_id = pet.id

    # 补归属：待补对象的提醒（quote 提到这只猫名）也归到它
    for rem in db.query(Reminder).filter(
        Reminder.status == "pending", Reminder.pet_id.is_(None)
    ).all():
        if mention_count(name, rem.quote) >= 1:
            rem.pet_id = pet.id

    db.commit()
    db.refresh(pet)
    return {"id": pet.id, "name": pet.name}
