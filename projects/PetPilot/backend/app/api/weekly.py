from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Fact, Pet, Photo, WeeklyReview
from app.services.summary import generate_weekly_review

router = APIRouter()


class WeeklyReviewIn(BaseModel):
    pet_id: int | None = None


@router.post("/weekly-review", status_code=201)
def create_weekly_review(
    body: WeeklyReviewIn,
    db: Session = Depends(get_db),
    sess=Depends(get_current_session),
):
    since = datetime.now() - timedelta(days=7)
    q = db.query(Fact).filter(Fact.created_at >= since)
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    if body.pet_id is not None:
        if body.pet_id not in pet_names:
            raise HTTPException(
                404, detail={"error": {"code": "PET_NOT_FOUND", "message": "猫不存在"}}
            )
        q = q.filter(Fact.pet_id == body.pet_id)
        label = pet_names[body.pet_id]
        title = f"{label} 周回顾"
    else:
        label = "全部猫"
        title = "周回顾（全部猫）"

    facts = q.order_by(Fact.created_at.asc()).all()

    photo_q = db.query(Photo).filter(Photo.created_at >= since)
    if body.pet_id is not None:
        photo_q = photo_q.filter(Photo.pet_id == body.pet_id)
    photos = photo_q.order_by(Photo.created_at.asc()).all()

    if not facts and not photos:
        raise HTTPException(
            409, detail={"error": {"code": "WEEKLY_EMPTY", "message": "近 7 天无记录，不生成周回顾"}}
        )

    summary = generate_weekly_review(label, facts, photos)
    wr = WeeklyReview(
        pet_id=body.pet_id,
        title=title,
        fact_ids=[f.id for f in facts],
        summary=summary,
    )
    db.add(wr)
    db.commit()
    db.refresh(wr)
    return {"id": wr.id, "pet_name": pet_names.get(wr.pet_id, "") if wr.pet_id else "全部猫", "title": wr.title, "summary": wr.summary}


@router.get("/weekly-reviews")
def list_weekly_reviews(
    db: Session = Depends(get_db), sess=Depends(get_current_session)
):
    pet_names = {p.id: p.name for p in db.query(Pet).all()}
    items = db.query(WeeklyReview).order_by(WeeklyReview.id.desc()).all()
    return {
        "weekly_reviews": [
            {
                "id": w.id,
                "pet_name": pet_names.get(w.pet_id, "全部猫") if w.pet_id else "全部猫",
                "title": w.title,
                "summary": w.summary,
            }
            for w in items
        ]
    }
