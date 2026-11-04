from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import Fact, HeldSegment, Message, Pet
from app.schemas import MessageIn, MessageResult
from app.services.attribution import resolve_operations
from app.services.model_client import ModelClient, ModelError, SchemaError

router = APIRouter()


def _receipt(facts_count: int, held_count: int) -> str:
    parts = []
    if facts_count:
        parts.append(f"已保存 {facts_count} 条记录")
    if held_count:
        parts.append(f"{held_count} 条记录归属未知，等待确认")
    return "，".join(parts) if parts else "已收到（本次没有产生记录）"


@router.post("/messages", response_model=MessageResult)
def send_message(
    body: MessageIn,
    db: Session = Depends(get_db),
    sess=Depends(get_current_session),
):
    text = body.text.strip()
    if not text:
        raise HTTPException(
            422, detail={"error": {"code": "VALIDATION_ERROR", "message": "消息不能为空"}}
        )

    pets = db.query(Pet).order_by(Pet.id).all()

    try:
        raw = ModelClient().extract(text, pets)
    except SchemaError as e:
        raise HTTPException(
            502, detail={"error": {"code": "SCHEMA_INVALID", "message": str(e)}}
        )
    except ModelError as e:
        raise HTTPException(
            502, detail={"error": {"code": "MODEL_FAILED", "message": str(e)}}
        )

    adds, holds = resolve_operations(raw.get("operations", []), text, pets)

    msg = Message(role="user", content=text)
    db.add(msg)
    db.flush()

    facts = []
    for op in adds:
        fact = Fact(
            pet_id=op["pet_id"],
            topic=op.get("topic"),
            value=op.get("value"),
            unit=op.get("unit"),
            quantity_scope=op.get("quantity_scope"),
            historical_current=op.get("historical_current"),
            occurred_at=op.get("occurred_at"),
            polarity=op.get("polarity"),
            change_kind="new",
            source_message_id=msg.id,
            quote=op.get("quote") or "",
            version=1,
        )
        db.add(fact)
        facts.append(fact)

    helds = []
    for op in holds:
        hs = HeldSegment(
            message_id=msg.id,
            quote=op.get("quote") or "",
            topic=op.get("topic"),
            reason="归属未知",
            status="pending",
        )
        db.add(hs)
        helds.append(hs)

    dialogue = raw.get("dialogue") or {}
    answer = (dialogue.get("answer") or {}).get("text", "")
    explanation = (dialogue.get("explanation") or {}).get("text", "")

    db.flush()

    receipt = _receipt(len(facts), len(helds))
    assistant_text = receipt
    if answer:
        assistant_text = f"{receipt}\n{answer}"
    db.add(Message(role="assistant", content=assistant_text))
    db.commit()

    pet_names = {p.id: p.name for p in pets}
    return {
        "message_id": msg.id,
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
        ],
        "held_segments": [
            {"id": h.id, "quote": h.quote, "reason": h.reason} for h in helds
        ],
        "answer": answer,
        "explanation": explanation,
        "receipt": receipt,
    }


@router.get("/messages")
def list_messages(
    db: Session = Depends(get_db), sess=Depends(get_current_session)
):
    msgs = db.query(Message).order_by(Message.id.asc()).all()
    return {
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content} for m in msgs
        ]
    }
