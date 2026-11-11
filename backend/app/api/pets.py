from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_owner_id
from app.services.attribution import mention_count
from app.services.repository import Repository, get_repo

router = APIRouter()


class PetCreate(BaseModel):
    name: str


@router.get("/pets")
def list_pets(
    repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)
):
    pets = repo.list_pets()
    return {"pets": [{"id": p.id, "name": p.name} for p in pets]}


@router.post("/pets", status_code=201)
def create_pet(
    body: PetCreate,
    repo: Repository = Depends(get_repo),
    sess=Depends(get_owner_id),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(
            422, detail={"error": {"code": "VALIDATION_ERROR", "message": "名字不能为空"}}
        )
    if repo.get_pet_by_name(name):
        raise HTTPException(
            409, detail={"error": {"code": "PET_NAME_DUPLICATE", "message": "已有同名猫"}}
        )
    pet = repo.create_pet(name)
    repo.flush()

    # 补归属（R11/R12）：把之前挂起的、提到这只猫的片段自动归到它名下
    for h in repo.list_pending_held():
        if mention_count(name, h.quote) >= 1:
            repo.create_fact(
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
            h.status = "resolved"
            h.resolved_pet_id = pet.id

    # 补归属：待补对象的提醒（quote 提到这只猫名）也归到它
    for rem in repo.list_reminders():
        if rem.status == "pending" and rem.pet_id is None and mention_count(name, rem.quote) >= 1:
            rem.pet_id = pet.id

    repo.commit()
    repo.refresh(pet)
    return {"id": pet.id, "name": pet.name}
