from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_owner_id
from app.services.repository import Repository, get_repo

router = APIRouter()

_SIMULATED_REPLY = (
    "【模拟医院回复】感谢您整理的资料，我们已收到，会尽快安排查看。"
    "（本回复为模拟内容，非真实医院发送，不代表真实接诊或预约。）"
)


@router.get("/care-summaries")
def list_summaries(
    repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)
):
    pet_names = {p.id: p.name for p in repo.list_pets()}
    items = repo.list_care_summaries()
    return {
        "care_summaries": [
            {
                "id": c.id,
                "pet_name": pet_names.get(c.pet_id, ""),
                "title": c.title,
                "summary": c.summary,
                "stale": c.stale,
            }
            for c in items
        ]
    }


@router.post("/care-summaries/{summary_id}/simulate-reply")
def simulate_reply(
    summary_id: int,
    repo: Repository = Depends(get_repo),
    sess=Depends(get_owner_id),
):
    cs = repo.get_care_summary(summary_id)
    if not cs:
        raise HTTPException(
            404, detail={"error": {"code": "CARE_NOT_FOUND", "message": "摘要不存在"}}
        )
    return {"reply": _SIMULATED_REPLY, "is_simulated": True}
