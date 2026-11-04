from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Pet
from app.schemas import PetCreate, PetOut

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
    db.commit()
    db.refresh(pet)
    return {"id": pet.id, "name": pet.name}
