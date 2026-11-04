import re

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


def _receipt(facts, held, corrections, reminders, cares, resolved=0) -> str:
    parts = []
    if facts:
        parts.append(f"已保存 {len(facts)} 条记录")
    if resolved:
        parts.append(f"已把 {resolved} 条挂起记录归到对应猫")
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

    held_context = [
        {"id": h.id, "quote": h.quote, "topic": h.topic, "value": h.value, "unit": h.unit}
        for h in db.query(HeldSegment).filter(HeldSegment.status == "pending").all()
    ]

    try:
        raw = ModelClient().extract(text, pets, facts_context, held_context)
    except SchemaError as e:
        raise HTTPException(
            502, detail={"error": {"code": "SCHEMA_INVALID", "message": str(e)}}
        )
    except ModelError as e:
        raise HTTPException(
            502, detail={"error": {"code": "MODEL_FAILED", "message": str(e)}}
        )

    adds, holds, corrections, resolves = resolve_operations(raw.get("operations", []), text, pets)
    dialogue = raw.get("dialogue") or {}

    # 确定性补归属：主人澄清“他指的是X” / “是X的”
    clarified_pet = None
    for pet in pets:
        if (
            f"指的是{pet.name}" in text
            or f"是{pet.name}的" in text
            or f"是给{pet.name}" in text
            or f"给{pet.name}的" in text
            or f"归到{pet.name}" in text
            or re.search(f"[他它她]是{pet.name}", text)
        ):
            clarified_pet = pet  # 不 break：口误更正时最后提到的猫优先

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

    # 2) 挂起（澄清消息本身不再挂起）
    helds = []
    if not clarified_pet:
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

    # 3.5) 补归属：主人澄清了之前挂起片段属于哪只猫
    resolved_facts = []
    resolved_held_ids = set()
    for rv in resolves:
        if rv["held_id"] in resolved_held_ids:
            continue
        h = db.query(HeldSegment).filter(
            HeldSegment.id == rv["held_id"], HeldSegment.status == "pending"
        ).first()
        if not h:
            continue
        resolved_held_ids.add(rv["held_id"])
        f = Fact(
            pet_id=rv["pet_id"],
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
        db.add(f)
        h.status = "resolved"
        h.resolved_pet_id = rv["pet_id"]
        resolved_facts.append(f)
    db.flush()  # 关键：把已解决的挂起状态刷到库，避免下面确定性规则重复归因

    # 确定性补归属：澄清“他指的是X/他是X” → 把仍挂起的片段 + 待补对象的提醒归到 X
    resolved_reminder_count = 0
    if clarified_pet:
        for h in db.query(HeldSegment).filter(HeldSegment.status == "pending").all():
            f = Fact(
                pet_id=clarified_pet.id,
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
            db.add(f)
            h.status = "resolved"
            h.resolved_pet_id = clarified_pet.id
            resolved_facts.append(f)
        for rem in db.query(Reminder).filter(
            Reminder.status == "pending", Reminder.pet_id.is_(None)
        ).all():
            rem.pet_id = clarified_pet.id
            resolved_reminder_count += 1

    # 4) 提醒
    reminder_results = []
    seen_reminder_quotes = set()
    for r in dialogue.get("reminders", []):
        quote = (r.get("quote") or "").strip()
        if not quote or quote not in text:
            continue
        if quote in seen_reminder_quotes:
            continue  # 去重：模型重复输出
        seen_reminder_quotes.add(quote)
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

    # 问题1：有未指定猫的提醒时，追问是哪只猫
    if any(rm.get("pet_name") is None for rm in reminder_results):
        followup = "另外，有提醒还没指定是哪只猫，请问是给谁？若暂时不确定，可以稍后到「提醒」页手动选择。"
        answer = f"{answer}\n{followup}" if answer else followup

    if resolved_reminder_count and clarified_pet:
        note = f"已把 {resolved_reminder_count} 个提醒归到「{clarified_pet.name}」。"
        answer = f"{answer}\n{note}" if answer else note

    receipt = _receipt(facts, helds, correction_results, reminder_results, care_results, len(resolved_facts))
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
            for f in facts + resolved_facts
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
