from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_current_session, get_db
from app.models import CareSummary, Correction, Fact, HeldSegment, Message, Pet, Reminder, WeeklyReview
from app.schemas import MessageIn, MessageResult
from app.services.attribution import mention_count, resolve_operations
from app.services.model_client import ModelClient, ModelError, SchemaError
from app.services.reminder_intent import is_authorized_reminder, parse_due_time
from app.services.summary import generate_care_summary

router = APIRouter()


def _extract_text(val):
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("text", "")
    return ""


def _receipt(facts, held, corrections, reminders, cares) -> str:
    parts = []
    if facts:
        parts.append(f"已保存 {len(facts)} 条记录")
    if corrections:
        parts.append(f"已纠错 {len(corrections)} 条")
    if reminders:
        parts.append(f"已设 {len(reminders)} 个提醒")
    if cares:
        parts.append(f"已整理 {len(cares)} 份就医摘要")
    if held:
        parts.append(f"{len(held)} 条记录归属未知，等待确认")
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
    pet_names = {p.id: p.name for p in pets}
    allowed_ids = set(pet_names.keys())

    recent_facts = db.query(Fact).order_by(Fact.id.desc()).limit(20).all()
    facts_context = [
        {
            "id": f.id,
            "pet_name": pet_names.get(f.pet_id, ""),
            "topic": f.topic,
            "value": f.value,
            "unit": f.unit,
            "quote": f.quote,
            "version": f.version,
        }
        for f in recent_facts
    ]

    try:
        raw = ModelClient().extract(text, pets, facts_context)
    except SchemaError as e:
        raise HTTPException(
            502, detail={"error": {"code": "SCHEMA_INVALID", "message": str(e)}}
        )
    except ModelError as e:
        raise HTTPException(
            502, detail={"error": {"code": "MODEL_FAILED", "message": str(e)}}
        )

    adds, holds, corrections = resolve_operations(raw.get("operations", []), text, pets)
    dialogue = raw.get("dialogue") or {}

    msg = Message(role="user", content=text)
    db.add(msg)
    db.flush()

    # 1) 新增观察
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

    # 2) 挂起
    helds = []
    for op in holds:
        hs = HeldSegment(
            message_id=msg.id,
            quote=op.get("quote") or "",
            topic=op.get("topic"),
            reason="归属未知",
            value=op.get("value"),
            unit=op.get("unit"),
            quantity_scope=op.get("quantity_scope"),
            historical_current=op.get("historical_current"),
            occurred_at=op.get("occurred_at"),
            polarity=op.get("polarity"),
            status="pending",
        )
        db.add(hs)
        helds.append(hs)

    db.flush()

    # 3) 纠错
    correction_results = []
    for c in corrections:
        fact = None
        if c.get("fact_id") is not None:
            fact = db.query(Fact).filter(Fact.id == c["fact_id"]).first()
        if not fact:
            continue
        if c.get("expected_version") is not None and fact.version != c["expected_version"]:
            correction_results.append(
                {"fact_id": fact.id, "status": "conflict", "message": "版本冲突，未更新"}
            )
            continue
        old_value, old_topic = fact.value, fact.topic
        new_value = c["value"] if c.get("value") is not None else fact.value
        new_topic = c.get("topic") or fact.topic
        db.add(
            Correction(
                fact_id=fact.id,
                old_value=old_value,
                new_value=new_value,
                old_topic=old_topic,
                new_topic=new_topic,
                quote=c.get("quote") or "",
                source_message_id=msg.id,
            )
        )
        fact.value = new_value
        fact.topic = new_topic
        if c.get("unit"):
            fact.unit = c["unit"]
        fact.quote = c.get("quote") or fact.quote
        fact.version += 1
        # R24：同步——引用该事实的摘要/周回顾标记为过期
        for s in db.query(CareSummary).all():
            if fact.id in (s.fact_ids or []):
                s.stale = True
        for w in db.query(WeeklyReview).all():
            if fact.id in (w.fact_ids or []):
                w.stale = True
        correction_results.append(
            {"fact_id": fact.id, "pet_id": fact.pet_id, "new_value": new_value, "version": fact.version, "status": "ok"}
        )

    # 4) 提醒
    reminder_results = []
    for r in dialogue.get("reminders", []):
        quote = (r.get("quote") or "").strip()
        if not quote or quote not in text:
            continue
        if not is_authorized_reminder(quote):
            continue  # 否定/假设/问句/引用不算授权
        due = parse_due_time(quote)
        pid = r.get("pet_id")
        # 服务端裁决：提醒对象必须整词匹配，未明确指定不猜猫（R36）
        mentioned = [p for p in pets if mention_count(p.name, quote) >= 1]
        if pid in allowed_ids and pid in {p.id for p in mentioned}:
            pass  # 明确提到，信任
        elif len(mentioned) == 1:
            pid = mentioned[0].id  # 明确表达优先
        else:
            pid = None  # 未指定 → 待补对象
        rem = Reminder(pet_id=pid, quote=quote, due_at=due, status="pending")
        db.add(rem)
        db.flush()
        reminder_results.append({
            "id": rem.id,
            "pet_name": pet_names.get(rem.pet_id, "") if rem.pet_id else None,
            "quote": quote,
            "due_at": due.strftime("%Y-%m-%d %H:%M") if due else None,
            "status": "pending",
        })

    # 5) 就医摘要
    care_results = []
    for cr in dialogue.get("care_requests", []):
        pid = cr.get("pet_id")
        if pid not in allowed_ids:
            continue
        fact_ids = cr.get("fact_ids") or []
        if fact_ids:
            sel_facts = db.query(Fact).filter(Fact.pet_id == pid, Fact.id.in_(fact_ids)).all()
        else:
            sel_facts = db.query(Fact).filter(Fact.pet_id == pid).order_by(Fact.id.desc()).limit(20).all()
        title = cr.get("title") or f"{pet_names[pid]}就医准备"
        summary_text = generate_care_summary(pet_names[pid], sel_facts)
        cs = CareSummary(
            pet_id=pid,
            title=title,
            fact_ids=[f.id for f in sel_facts],
            summary=summary_text,
            source_message_id=msg.id,
        )
        db.add(cs)
        db.flush()
        care_results.append({"id": cs.id, "pet_name": pet_names[pid], "title": title, "summary": summary_text})

    answer = _extract_text(dialogue.get("answer"))
    explanation = _extract_text(dialogue.get("explanation"))

    receipt = _receipt(facts, helds, correction_results, reminder_results, care_results)
    assistant_text = receipt
    if answer:
        assistant_text = f"{receipt}\n{answer}"
    db.add(Message(role="assistant", content=assistant_text))
    db.commit()

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
        "corrections": correction_results,
        "reminders": reminder_results,
        "care_requests": care_results,
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
