import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import settings
from app.dependencies import get_owner_id
from app.models import Fact, HeldSegment, Photo
from app.schemas import MessageResult
from app.services.attribution import mention_count, mentioned_pets, resolve_operations
from app.services.model_client import ModelClient, ModelError, SchemaError
from app.services.reminder_intent import _cn_to_int, is_authorized_reminder, parse_due_time
from app.services.repository import Repository, get_repo
from app.services.storage import save_image, validate_image
from app.services.summary import generate_care_summary

router = APIRouter()

_SIMULATED_REPLY = (
    "【模拟医院回复】感谢您整理的资料，我们已收到，会尽快安排查看。"
    "（本回复为模拟内容，非真实医院发送，不代表真实接诊或预约。）"
)

_UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "uploads",
)


def _extract_text(val):
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("text", "")
    return ""


def _negated(text: str, keyword: str) -> bool:
    """检测 keyword 是否被否定词（不要/别/不用/不）修饰，如“不要整理”“别发送”。"""
    return re.search(rf"(不要|不用|别|不)[^，。！？；,.!?；\s]{{0,8}}{keyword}", text) is not None


def _to_date(dt):
    """把时间转成 date（带时区先转本地时区再取日期）。"""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone().date()
    return dt.date()


def _safe_care_summary(pet_name: str, facts: list) -> tuple[bool, str]:
    """生成就医摘要；返回 (是否成功, 文本)。失败或空结果都不当作正式成果。"""
    try:
        text = generate_care_summary(pet_name, facts)
        if not text or not text.strip():
            return False, f"{pet_name}的就医摘要生成失败"
        return True, text
    except Exception:
        return False, f"{pet_name}的就医摘要生成失败"


def _build_history(repo: Repository, max_chars: int = 6000) -> list[dict]:
    """取最近 user/assistant 消息（时间正序，不含当前消息），单条截断、合计不超过 max_chars，从最早裁。"""
    rows = repo.list_recent_messages(20)
    picked: list[dict] = []
    total = 0
    for m in rows:  # rows 已按最新在前
        c = (m.content or "")[:1500]  # 单条截断，避免超长内容撑爆上下文
        if total + len(c) > max_chars and picked:
            break
        picked.append({"role": m.role, "content": c})
        total += len(c)
    picked.reverse()
    return picked


def _receipt(facts, held, corrections, reminders, cares, photos=0, resolved=0) -> str:
    parts = []
    if facts:
        parts.append(f"已保存 {len(facts)} 条记录")
    if photos:
        parts.append(f"已保存 {photos} 张照片")
    if resolved:
        parts.append(f"已把 {resolved} 条挂起记录归到对应猫")
    if corrections:
        ok_corrections = sum(1 for c in corrections if c.get("status") == "ok")
        if ok_corrections:
            parts.append(f"已纠错 {ok_corrections} 条")
    if reminders:
        parts.append(f"已设 {len(reminders)} 个提醒")
    if cares:
        parts.append(f"已整理 {len(cares)} 份就医摘要")
    if held:
        parts.append(f"{len(held)} 条记录归属未知，等待确认")
    return "，".join(parts) if parts else "已收到（本次没有产生记录）"


@router.post("/messages", response_model=MessageResult)
async def send_message(
    text: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    repo: Repository = Depends(get_repo),
    sess=Depends(get_owner_id),
):
    text = text.strip()
    if not text and not files:
        raise HTTPException(
            422, detail={"error": {"code": "VALIDATION_ERROR", "message": "消息不能为空"}}
        )

    pets = repo.list_pets()
    pet_names = {p.id: p.name for p in pets}
    allowed_ids = set(pet_names.keys())

    # 最近对话历史（供模型理解指代与承接；当前消息尚未保存，不会重复）
    history = _build_history(repo)

    # 最近事实：按猫分组，当前消息提到的猫优先，每只猫最多 8 条，总量 20 条
    mentioned_ids = {p.id for p in pets if mention_count(p.name, text) >= 1}
    buckets: dict[int, list[Fact]] = {}
    for f in repo.list_recent_facts(60):
        buckets.setdefault(f.pet_id, []).append(f)
    flat_facts: list[Fact] = []
    for pid in sorted(buckets, key=lambda x: (x not in mentioned_ids, x)):
        flat_facts.extend(buckets[pid][:8])
        if len(flat_facts) >= 20:
            break
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
        for f in flat_facts[:20]
    ]
    held_context = [
        {"id": h.id, "quote": h.quote, "topic": h.topic, "value": h.value, "unit": h.unit}
        for h in repo.list_pending_held()
    ]

    msg = repo.create_message("user", text or "[图片]")
    repo.flush()

    # 保存照片（最多 5 张，关联到本条消息）
    saved_photos: list[Photo] = []
    rejected_files = 0
    for f in files[:5]:
        content = await f.read()
        if validate_image(content, f.filename or "") is not None:
            rejected_files += 1
            continue
        safe_name, path = save_image(content, f.filename or "", _UPLOADS_DIR)
        photo = repo.create_photo(filename=safe_name, stored_path=path, description="", message_id=msg.id)
        saved_photos.append(photo)
    photo_count = len(saved_photos)
    repo.flush()

    # 每日生成上限（预算护栏，按决策台账 D4）
    if settings.daily_generation_limit > 0 and text:
        today = datetime.now().date()
        recent = [m for m in repo.list_recent_messages(300) if m.role == "assistant" and m.created_at]
        today_count = sum(1 for m in recent if _to_date(m.created_at) == today)
        if today_count >= settings.daily_generation_limit:
            raise HTTPException(
                429, detail={"error": {"code": "DAILY_LIMIT", "message": "今日生成次数已达上限，请明天再试"}}
            )

    raw = {"operations": [], "dialogue": {}}
    if text:
        try:
            raw = ModelClient().extract(text, pets, facts_context, held_context, photo_count, history)
        except SchemaError as e:
            repo.delete_message(msg.id)
            raise HTTPException(
                502, detail={"error": {"code": "SCHEMA_INVALID", "message": str(e)}}
            )
        except ModelError as e:
            repo.delete_message(msg.id)
            raise HTTPException(
                502, detail={"error": {"code": "MODEL_FAILED", "message": str(e)}}
            )

    adds, holds, corrections, resolves = resolve_operations(raw.get("operations", []), text, pets)
    dialogue = raw.get("dialogue") or {}

    # 提醒补归属由原话授权，确认结果以实际更新为准。
    reminder_assignment = "提醒" in text and ("归" in text or re.search(r"提醒.{0,12}是", text) is not None)
    clarified_pet = None
    for pet in pets:
        if (
            f"指的是{pet.name}" in text
            or f"是{pet.name}的" in text
            or f"是给{pet.name}" in text
            or f"给{pet.name}的" in text
            or re.search(rf"归(?:到|给)?\s*{re.escape(pet.name)}(?![A-Za-z0-9])", text)
            or f"叫{pet.name}" in text
            or re.search(f"[他它她]是{pet.name}", text)
            or text.strip().endswith(f"是{pet.name}")
        ):
            clarified_pet = pet  # 不 break：口误更正时最后提到的猫优先
    if clarified_pet and _negated(re.sub(r"\s+", "", text), clarified_pet.name):
        clarified_pet = None

    if reminder_assignment and re.search(r"[?？]|[吗么][。！!\s]*$", text):
        clarified_pet = None

    # 1) 新增观察
    facts = []
    for op in adds:
        fact = repo.create_fact(
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
        facts.append(fact)

    # 2) 挂起（澄清消息本身不再挂起）
    helds = []
    if not clarified_pet:
        for op in holds:
            hs = repo.create_held(
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
            helds.append(hs)

    repo.flush()

    # 3) 纠错
    correction_results = []
    for c in corrections:
        fact = None
        if c.get("fact_id") is not None:
            fact = repo.get_fact(c["fact_id"])
        if not fact:
            continue
        # 跨猫校验：纠错 quote 里提到的猫必须包含目标事实的猫，否则是改错猫，拒绝
        corr_quote = c.get("quote") or ""
        corr_mentioned = mentioned_pets(corr_quote, pets)
        if corr_mentioned and fact.pet_id not in {p.id for p in corr_mentioned}:
            correction_results.append(
                {"fact_id": fact.id, "status": "conflict", "message": "跨猫纠错，未更新"}
            )
            continue
        if c.get("expected_version") is not None and fact.version != c["expected_version"]:
            correction_results.append(
                {"fact_id": fact.id, "status": "conflict", "message": "版本冲突，未更新"}
            )
            continue
        old_value, old_topic = fact.value, fact.topic
        new_value = c["value"] if c.get("value") is not None else fact.value
        new_topic = c.get("topic") or fact.topic
        repo.create_correction(
            fact_id=fact.id,
            old_value=old_value,
            new_value=new_value,
            old_topic=old_topic,
            new_topic=new_topic,
            quote=c.get("quote") or "",
            source_message_id=msg.id,
        )
        fact.value = new_value
        fact.topic = new_topic
        if c.get("unit"):
            fact.unit = c["unit"]
        fact.quote = c.get("quote") or fact.quote
        fact.version += 1
        for s in repo.list_care_summaries():
            if fact.id in (s.fact_ids or []):
                s.stale = True
        for w in repo.list_weekly_reviews():
            if fact.id in (w.fact_ids or []):
                w.stale = True
        correction_results.append(
            {"fact_id": fact.id, "pet_id": fact.pet_id, "new_value": new_value, "version": fact.version, "status": "ok"}
        )

    # 3.5) 补归属
    resolved_facts = []
    resolved_held_ids = set()
    for rv in resolves:
        if rv["held_id"] in resolved_held_ids:
            continue
        h = repo.get_pending_held(rv["held_id"])
        if not h:
            continue
        # 点名提醒时，模型不能顺带归属未被原话引用的记录。
        if reminder_assignment and h.quote not in text:
            continue
        resolved_held_ids.add(rv["held_id"])
        f = repo.create_fact(
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
        h.status = "resolved"
        h.resolved_pet_id = rv["pet_id"]
        resolved_facts.append(f)
    repo.flush()

    # 补归属按对象选择，记录数量不能证明提醒、照片与本次澄清有关。
    resolved_reminder_count = 0
    resolved_photo_count = 0
    clarified_ambiguous = False
    attribution_followups = []
    if clarified_pet:
        pending_reminders = [r for r in repo.list_reminders() if r.status == "pending" and r.pet_id is None]
        pending_photos = [p for p in repo.list_photos() if p.pet_id is None and p not in saved_photos]

        pending_helds = sorted(repo.list_pending_held(), key=lambda h: h.id)
        generic_pointer = any(word in text for word in ("那条", "这条", "这个"))
        explicit_kind = "提醒" in text or "照片" in text
        pending_count = len(pending_reminders) + len(pending_photos) + len(pending_helds)
        unique_pointer = generic_pointer and not explicit_kind and pending_count == 1 and not resolves
        if generic_pointer and not explicit_kind and pending_count > 1 and not resolves:
            attribution_followups.append("请说明要补归属的是哪条记录、提醒或照片")

        def select_targets(candidates, kind, source_field):
            # 只接受本轮引用的完整来源，或明确点名且唯一的该类对象。
            # 未点名对象类型的指代，仅在所有待归属对象中唯一时承接。
            has_pointer = kind in text or unique_pointer
            if not has_pointer or _negated(text, kind):
                return []
            quoted = [obj for obj in candidates if getattr(obj, source_field, "")
                      and getattr(obj, source_field) in text]
            if len(quoted) == 1:
                return quoted
            if len(candidates) == 1:
                return candidates
            if candidates:
                attribution_followups.append(f"有多条待确认{kind}，请说明是哪一条")
            return []

        target_reminders = select_targets(pending_reminders, "提醒", "quote")
        target_photos = select_targets(pending_photos, "照片", "description")
        # 按 id 正序（最早说的在前），“第一只/第一条”才对得上时间顺序
        m = re.search(r"第([一二两三四五六七八九十\d]+)[只条个]", text)
        if resolves:
            # 模型已用 resolve_held 精确选择了片段，兜底不再处理剩余片段
            target_helds = []
        elif m:
            idx = _cn_to_int(m.group(1)) - 1
            target_helds = [pending_helds[idx]] if 0 <= idx < len(pending_helds) else []
        elif explicit_kind or (generic_pointer and (pending_reminders or pending_photos)):
            # 明确在确认另一类对象，不能顺便处理唯一的挂起记录。
            target_helds = []
        elif len(pending_helds) <= 1:
            target_helds = pending_helds
        else:
            # 多条、无精确指代 → 不批量，澄清
            target_helds = []
            clarified_ambiguous = bool(pending_helds)
        for h in target_helds:
            f = repo.create_fact(
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
            h.status = "resolved"
            h.resolved_pet_id = clarified_pet.id
            resolved_facts.append(f)
        # 短答只能承接紧邻的一次、对象唯一的归属追问；从持久化消息核实来源。
        previous = [item for item in repo.list_recent_messages(3) if item.id != msg.id]
        identity_answer = re.fullmatch(
            rf"(?:[他它她](?:指的)?是|是给|给|归到|指的是|是){re.escape(clarified_pet.name)}(?:的)?[。！!]?",
            text,
        )
        if (not resolves and not pending_helds and not m and len(previous) == 2
                and identity_answer):
            question, source = previous
            if question.role == "assistant" and source.role == "user":
                reminder_question = "有提醒还没指定是哪只猫，请问是给谁？" in question.content
                photo_question = "张照片还不确定是哪只猫的，请告诉我" in question.content
                if reminder_question and not photo_question and not target_photos:
                    matches = [r for r in pending_reminders if r.quote == source.content]
                    if len(matches) == 1:
                        target_reminders = matches
                if photo_question and not reminder_question and not target_reminders:
                    matches = [p for p in pending_photos if p.message_id == source.id]
                    if len(matches) == 1:
                        target_photos = matches
        due_from_text = parse_due_time(text)
        for rem in target_reminders:
            rem.pet_id = clarified_pet.id
            resolved_reminder_count += 1
            if rem.due_at is None and due_from_text:
                rem.due_at = due_from_text
        for ph in target_photos:
            ph.pet_id = clarified_pet.id
            resolved_photo_count += 1

    # 纯时间短答只更新已有任务，不能作为新提醒，也不能承接无关日程。
    time_reply = re.fullmatch(
        r"(?:那就|就)?(?:定在|定到)?(?:今天|明天|后天)?\s*"
        r"(?:上午|下午|晚上|中午|早上|早晨)?\s*"
        r"(?:[0-9]+|[一二两三四五六七八九十]+)\s*点"
        r"(?:半|\s*(?:[0-9]+|[一二两三四五六七八九十]+)\s*分)?"
        r"\s*(?:吧|好了)?[。！!]?", text.strip(),
    ) is not None
    completed_time_reminder = None
    time_reply_answer = None
    if time_reply:
        due_from_short = parse_due_time(text)
        no_time = [r for r in repo.list_reminders() if r.status == "pending" and r.due_at is None]
        if due_from_short and len(no_time) == 1:
            completed_time_reminder = no_time[0]
            completed_time_reminder.due_at = due_from_short
            time_reply_answer = f"好的，已把「{completed_time_reminder.quote}」的提醒时间补为 {due_from_short:%Y-%m-%d %H:%M}。"
        elif len(no_time) > 1:
            time_reply_answer = "有多条提醒还缺时间，请说明要给哪条提醒补时间。"
        else:
            time_reply_answer = "目前没有可补时间的提醒，请把提醒事项和具体时间一起告诉我。"

    # 4) 提醒
    reminder_results = []
    seen_reminder_quotes = set()
    # “明天上午9点，是明月”这类补时间/补猫的短答，不新建提醒，只补到已有 pending 提醒
    clarify_short = clarified_pet is not None and any(text.strip().endswith(f"是{p.name}") for p in pets)
    for r in dialogue.get("reminders", []):
        if clarify_short or time_reply:
            continue
        quote = (r.get("quote") or "").strip()
        if not quote or quote not in text:
            continue
        if quote in seen_reminder_quotes:
            continue
        seen_reminder_quotes.add(quote)
        if not is_authorized_reminder(quote):
            continue
        due = parse_due_time(quote)
        pid = r.get("pet_id")
        mentioned = [p for p in pets if mention_count(p.name, quote) >= 1]
        if pid in allowed_ids and pid in {p.id for p in mentioned}:
            pass
        elif len(mentioned) == 1:
            pid = mentioned[0].id
        else:
            pid = None
        rem = repo.create_reminder(pet_id=pid, quote=quote, due_at=due, status="pending")
        repo.flush()
        reminder_results.append({
            "id": rem.id,
            "pet_name": pet_names.get(rem.pet_id, "") if rem.pet_id else None,
            "quote": quote,
            "due_at": due.strftime("%Y-%m-%d %H:%M") if due else None,
            "status": "pending",
        })

    # 5) 就医摘要
    care_results = []
    care_failed = False
    unattributed_care = False
    for cr in dialogue.get("care_requests", []):
        pid = cr.get("pet_id")
        mentioned = [p for p in pets if mention_count(p.name, text) >= 1]
        if pid in allowed_ids and (pid in {p.id for p in mentioned} or len(pets) == 1):
            pass  # 有效 pid 且（当前提到它 或 只有一只猫）
        elif len(pets) == 1:
            pid = pets[0].id  # 单猫：模型没给有效 pid，用唯一猫
        elif len(mentioned) == 1:
            pid = mentioned[0].id
        else:
            unattributed_care = True
            continue
        fact_ids = cr.get("fact_ids") or []
        if fact_ids:
            sel_facts = [f for f in repo.list_facts(pid) if f.id in fact_ids]
        else:
            sel_facts = repo.list_facts(pid)[:20]
        title = cr.get("title") or f"{pet_names[pid]}就医准备"
        ok, summary_text = _safe_care_summary(pet_names[pid], sel_facts)
        if not ok:
            care_failed = True
            continue  # 生成失败：不保存为正式摘要
        cs = repo.create_care_summary(
            pet_id=pid,
            title=title,
            fact_ids=[f.id for f in sel_facts],
            summary=summary_text,
            source_message_id=msg.id,
        )
        repo.flush()
        care_results.append({"id": cs.id, "pet_name": pet_names[pid], "title": title, "summary": summary_text})

    # 5.5) 确定性兜底：主人要求“整理摘要”但模型没输出 care_requests 时，按上下文推断猫并生成
    care_intent = ("整理" in text) and ("好了" not in text) and not _negated(text, "整理")
    if care_intent and not care_results:
        target_pid = None
        mentioned = [p for p in pets if mention_count(p.name, text) >= 1]
        if len(mentioned) == 1:
            target_pid = mentioned[0].id
        elif len(pets) == 1:
            target_pid = pets[0].id
        else:
            recent_ids = {f.pet_id for f in repo.list_recent_facts(10)}
            if len(recent_ids) == 1:
                target_pid = next(iter(recent_ids))
        if target_pid is not None:
            sel_facts = repo.list_facts(target_pid)[:20]
            if sel_facts:
                ok, summary_text = _safe_care_summary(pet_names[target_pid], sel_facts)
                if ok:
                    cs = repo.create_care_summary(
                        pet_id=target_pid,
                        title=f"{pet_names[target_pid]}就医摘要",
                        fact_ids=[f.id for f in sel_facts],
                        summary=summary_text,
                        source_message_id=msg.id,
                    )
                    repo.flush()
                    care_results.append({"id": cs.id, "pet_name": pet_names[target_pid], "title": cs.title, "summary": summary_text})
                else:
                    care_failed = True
                unattributed_care = False
            else:
                unattributed_care = True
        else:
            unattributed_care = True

    # 6) 照片归属
    if saved_photos:
        mentioned_names = [p.name for p in pets if mention_count(p.name, text) >= 1] if text else []
        if len(mentioned_names) == 1:
            pid = next(p.id for p in pets if p.name == mentioned_names[0])
            for ph in saved_photos:
                ph.pet_id = pid
        else:
            for pa in dialogue.get("photo_attributions", []):
                try:
                    start = int(pa.get("start", 1))
                    end = int(pa.get("end", start))
                    pid = pa.get("pet_id")
                except (TypeError, ValueError):
                    continue
                if pid not in allowed_ids:
                    continue
                for ph in saved_photos[start - 1 : end]:
                    if ph.pet_id is None:
                        ph.pet_id = pid
    repo.flush()

    answer = _extract_text(dialogue.get("answer"))
    explanation = _extract_text(dialogue.get("explanation"))
    if reminder_assignment and not resolved_reminder_count and not reminder_results:
        answer = "本次未修改提醒归属。请确认待处理提醒和完整猫名，也可到「提醒」页选猫。"

    if any(r["due_at"] is None for r in reminder_results):
        answer = "提醒事项已保存，具体时间待补充。"

    elif any(r["pet_name"] is None for r in reminder_results):
        answer = "提醒已保存，猫的归属待确认。"

    if time_reply_answer:
        answer = time_reply_answer
    elif clarified_pet and (resolved_facts or resolved_reminder_count or resolved_photo_count):
        parts = []
        if resolved_facts:
            parts.append(f"{len(resolved_facts)} 条挂起记录")
        if resolved_reminder_count:
            parts.append(f"{resolved_reminder_count} 个提醒")
        if resolved_photo_count:
            parts.append(f"{resolved_photo_count} 张照片")
        answer = f"好的，已把 {'、'.join(parts)} 归到「{clarified_pet.name}」。"
    elif "建好" in text:
        # 主人说"建好了"：确认已关联到猫的提醒
        linked = [r for r in repo.list_reminders() if r.status == "pending" and r.pet_id is not None]
        if linked:
            items = "、".join(
                f"「{pet_names.get(r.pet_id, '')}」{r.quote}" for r in linked[:3]
            )
            answer = f"好的，已关联提醒：{items}。"
    elif ("发送" in text or "发给" in text or "外发" in text) and not _negated(text, "发送") and not _negated(text, "发给") and not _negated(text, "外发"):
        answer = _SIMULATED_REPLY
    else:
        followups = []
        if any(rm.get("pet_name") is None for rm in reminder_results):
            followups.append("有提醒还没指定是哪只猫，请问是给谁？可稍后到「提醒」页处理")
        if any(rm.get("due_at") is None for rm in reminder_results):
            followups.append("有提醒还没指定具体时间，请问是几点？可稍后到「提醒」页处理")
        if helds:
            followups.append(f"有 {len(helds)} 条记录还不确定是哪只猫，请告诉我是哪只猫的，或稍后到「记录-未确认」页手动补归属")
        if saved_photos and any(ph.pet_id is None for ph in saved_photos):
            followups.append(f"有 {sum(1 for ph in saved_photos if ph.pet_id is None)} 张照片还不确定是哪只猫的，请告诉我")
        if rejected_files:
            followups.append(f"有 {rejected_files} 个文件不是合法图片，已跳过")
        if care_failed:
            followups.append("记录已保存，但就医摘要生成失败，请稍后重新尝试")
        if clarified_ambiguous:
            followups.append("有多条待确认记录，请告诉我是哪一条")
        followups.extend(attribution_followups)
        if unattributed_care:
            followups.append("请问是整理哪只猫的就医摘要？")
            answer = ""
        if followups:
            content = "；".join(followups)
            answer = (answer + "\n另外，" + content) if answer else content

    # 就医摘要文字直接进聊天（不再有独立摘要页）
    if care_results:
        summaries = "\n\n".join(f"【{c['title']}】\n{c['summary']}" for c in care_results)
        answer = (answer + "\n\n" if answer else "") + summaries

    photo_results = [
        {"id": ph.id, "pet_id": ph.pet_id, "pet_name": pet_names.get(ph.pet_id, "") if ph.pet_id else None, "filename": ph.filename}
        for ph in saved_photos
    ]

    receipt = _receipt(facts, helds, correction_results, reminder_results, care_results, len(photo_results), len(resolved_facts))
    if completed_time_reminder:
        receipt = "已补全 1 个提醒的时间"
    elif resolved_reminder_count:
        receipt = f"已补全 {resolved_reminder_count} 个提醒的归属"
    assistant_text = f"{answer}\n{receipt}" if answer else receipt
    repo.create_message("assistant", assistant_text)
    repo.commit()

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
        "photos": photo_results,
        "answer": answer,
        "explanation": explanation,
        "receipt": receipt,
    }


@router.get("/messages")
def list_messages(
    repo: Repository = Depends(get_repo), sess=Depends(get_owner_id)
):
    msgs = sorted(repo.list_recent_messages(1000), key=lambda m: m.id)
    all_photos = repo.list_photos()
    photos_by_msg: dict = {}
    for p in all_photos:
        photos_by_msg.setdefault(p.message_id, []).append(
            {"id": p.id, "filename": p.filename, "pet_id": p.pet_id}
        )
    return {
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "photos": photos_by_msg.get(m.id, [])}
            for m in msgs
        ]
    }
