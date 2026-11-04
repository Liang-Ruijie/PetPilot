import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Pet, Photo
from app.services.storage import save_image, validate_image

router = APIRouter()

_UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "uploads",
)


@router.post("/photos", status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    pet_id: int | None = Form(default=None),
    description: str = Form(default=""),
    db: Session = Depends(get_db),
    sess=Depends(get_current_session),
):
    content = await file.read()
    err = validate_image(content, file.filename or "")
    if err:
        raise HTTPException(
            422, detail={"error": {"code": "FILE_TYPE_INVALID", "message": err}}
        )
    safe_name, path = save_image(content, file.filename or "", _UPLOADS_DIR)
    if pet_id is not None and not db.query(Pet).filter(Pet.id == pet_id).first():
        pet_id = None
    photo = Photo(
        pet_id=pet_id,
        filename=safe_name,
        stored_path=path,
        description=description.strip(),
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    return {
        "id": photo.id,
        "pet_name": pet_names.get(photo.pet_id, "") if photo.pet_id else None,
        "filename": photo.filename,
        "description": photo.description,
    }


@router.get("/photos")
def list_photos(
    db: Session = Depends(get_db), sess=Depends(get_current_session)
):
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    photos = db.query(Photo).order_by(Photo.id.desc()).all()
    return {
        "photos": [
            {
                "id": p.id,
                "pet_name": pet_names.get(p.pet_id, "") if p.pet_id else None,
                "filename": p.filename,
                "description": p.description,
            }
            for p in photos
        ]
    }
