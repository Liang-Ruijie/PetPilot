import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Fact, Pet, Photo
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
    desc = description.strip()
    photo = Photo(
        pet_id=pet_id,
        filename=safe_name,
        stored_path=path,
        description=desc,
    )
    db.add(photo)
    # 照片描述同时生成一条文字记录，归到这只猫（照片描述进记录）
    if desc and pet_id is not None:
        db.add(
            Fact(
                pet_id=pet_id,
                topic="照片记录",
                value=None,
                unit=None,
                change_kind="new",
                source_message_id=None,
                quote=desc,
                version=1,
            )
        )
    db.commit()
    db.refresh(photo)
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    return {
        "id": photo.id,
        "pet_name": pet_names.get(photo.pet_id, "") if photo.pet_id else None,
        "filename": photo.filename,
        "description": photo.description,
    }


@router.get("/photos/{photo_id}/file")
def get_photo_file(photo_id: int, db: Session = Depends(get_db), sess=Depends(get_current_session)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(
            404, detail={"error": {"code": "PHOTO_NOT_FOUND", "message": "照片不存在"}}
        )
    return FileResponse(photo.stored_path)


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
