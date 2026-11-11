from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_owner_id
from app.services.repository import Repository, get_repo

router = APIRouter()


class ResolveHeld(BaseModel):
    pet_id: int


@router.post("/clear-data")
def clear_data(repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)):
    """清空当前用户空间的所有业务数据（猫、记录、提醒、消息、摘要等）。"""
    repo.clear_owner(sess)
    return {"ok": True}


@router.get("/facts")
def list_facts(
    pet_id: int | None = None,
    repo: Repository = Depends(get_repo),
    sess=Depends(get_owner_id),
):
    if pet_id is not None:
        if repo.get_pet(pet_id) is None:
            raise HTTPException(
                404, detail={"error": {"code": "PET_NOT_FOUND", "message": "猫不存在"}}
            )
    facts = repo.list_facts(pet_id)
    pet_names = {p.id: p.name for p in repo.list_pets()}
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
    repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)
):
    helds = repo.list_pending_held()
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
    repo: Repository = Depends(get_repo),
    sess=Depends(get_owner_id),
):
    h = repo.get_pending_held(held_id)
    if not h:
        raise HTTPException(
            404, detail={"error": {"code": "HELD_NOT_FOUND", "message": "挂起片段不存在"}}
        )
    if repo.get_pet(body.pet_id) is None:
        raise HTTPException(
            404, detail={"error": {"code": "PET_NOT_FOUND", "message": "猫不存在"}}
        )
    fact = repo.create_fact(
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
    h.status = "resolved"
    h.resolved_pet_id = body.pet_id
    repo.commit()
    return {"id": fact.id, "pet_id": fact.pet_id}
