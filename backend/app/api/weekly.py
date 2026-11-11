from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_owner_id
from app.services.repository import Repository, get_repo
from app.services.summary import generate_weekly_review

router = APIRouter()


def _naive(dt):
    """把带时区的时间转成无时区本地时间，统一与本地 since 比较的口径。"""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


class WeeklyReviewIn(BaseModel):
    pet_id: int | None = None


@router.post("/weekly-review", status_code=201)
def create_weekly_review(
    body: WeeklyReviewIn,
    repo: Repository = Depends(get_repo),
    sess=Depends(get_owner_id),
):
    since = datetime.now() - timedelta(days=7)
    pet_names = {p.id: p.name for p in repo.list_pets()}
    if body.pet_id is not None:
        if body.pet_id not in pet_names:
            raise HTTPException(
                404, detail={"error": {"code": "PET_NOT_FOUND", "message": "猫不存在"}}
            )
        label = pet_names[body.pet_id]
        title = f"{label} 周回顾"
    else:
        label = "全部猫"
        title = "周回顾（全部猫）"

    facts = sorted(
        (f for f in repo.list_facts(body.pet_id) if f.created_at and _naive(f.created_at) >= since),
        key=lambda f: f.created_at,
    )
    photos = sorted(
        (p for p in repo.list_photos(body.pet_id) if p.created_at and _naive(p.created_at) >= since),
        key=lambda p: p.created_at,
    )

    if not facts and not photos:
        raise HTTPException(
            409, detail={"error": {"code": "WEEKLY_EMPTY", "message": "近 7 天无记录，不生成周回顾"}}
        )

    try:
        summary = generate_weekly_review(label, facts, len(photos))
    except Exception:
        raise HTTPException(
            502, detail={"error": {"code": "WEEKLY_FAILED", "message": "周回顾生成失败，请稍后重试"}}
        )
    if not summary or not summary.strip():
        raise HTTPException(
            502, detail={"error": {"code": "WEEKLY_FAILED", "message": "周回顾生成失败，请稍后重试"}}
        )
    wr = repo.create_weekly_review(
        pet_id=body.pet_id,
        title=title,
        fact_ids=[f.id for f in facts],
        summary=summary,
    )
    repo.commit()
    repo.refresh(wr)
    return {"id": wr.id, "pet_name": pet_names.get(wr.pet_id, "") if wr.pet_id else "全部猫", "title": wr.title, "summary": wr.summary}


@router.get("/weekly-reviews")
def list_weekly_reviews(
    repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)
):
    pet_names = {p.id: p.name for p in repo.list_pets()}
    items = repo.list_weekly_reviews()
    return {
        "weekly_reviews": [
            {
                "id": w.id,
                "pet_name": pet_names.get(w.pet_id, "全部猫") if w.pet_id else "全部猫",
                "title": w.title,
                "summary": w.summary,
                "stale": w.stale,
            }
            for w in items
        ]
    }
