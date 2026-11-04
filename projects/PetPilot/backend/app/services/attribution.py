from datetime import date, datetime

from app.models import Pet
from app.services.quote import is_valid_quote


def _is_boundary(ch: str | None) -> bool:
    """名字后面的字符不是 ASCII 字母/数字才算词边界，避免「贝塔」匹配「贝塔2」。"""
    if ch is None or ch == "":
        return True
    return not (ch.isascii() and ch.isalnum())


def mention_count(name: str, text: str) -> int:
    count = 0
    idx = 0
    while True:
        idx = text.find(name, idx)
        if idx == -1:
            break
        end = idx + len(name)
        nxt = text[end] if end < len(text) else None
        if _is_boundary(nxt):
            count += 1
        idx = end
    return count


def mentioned_pets(text: str, pets: list[Pet]) -> list[Pet]:
    return [p for p in pets if mention_count(p.name, text) >= 1]


def _near_miss(name: str, text: str) -> bool:
    """名字作为子串出现但不是整词（如「贝塔2」里含「贝塔」），模型可能做了子串匹配。"""
    return name in text and mention_count(name, text) == 0


def parse_occurred_date(s: str | None) -> date | None:
    """即时观察没写日期 → 按当天（R19）；有明确日期则保留。"""
    if not s:
        return date.today()
    s = str(s).strip()
    if s in ("today", "今天"):
        return date.today()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(s)
    except ValueError:
        return date.today()


def resolve_operations(operations: list[dict], text: str, pets: list[Pet]):
    """服务端裁决：pet_id 必须整词匹配；quote 必须落在原文；明确表达优先。"""
    allowed = {p.id: p for p in pets}
    mentioned = mentioned_pets(text, pets)
    mentioned_ids = {p.id for p in mentioned}
    adds: list[dict] = []
    holds: list[dict] = []

    for op in operations:
        kind = op.get("kind") or "add_observation"  # 宽容：模型缺 kind 默认按 add_observation 处理
        if kind == "add_observation":
            quote = (op.get("quote") or "").strip()
            if not is_valid_quote(quote, text):
                continue  # 丢弃不合法 quote
            pid = op.get("pet_id")
            if pid in allowed and pid in mentioned_ids:
                pass  # 明确提到，信任
            elif pid in allowed and _near_miss(allowed[pid].name, text):
                holds.append({"quote": quote, "topic": op.get("topic")})  # 近名非整词，挂起
                continue
            elif len(mentioned) == 1:
                pid = mentioned[0].id  # 明确表达优先
            elif pid in allowed and len(pets) == 1:
                pass  # 唯一猫，代词场景（如“它今天吃了26克”）
            else:
                holds.append({"quote": quote, "topic": op.get("topic")})
                continue
            op["pet_id"] = pid
            op["occurred_at"] = parse_occurred_date(op.get("occurred_at"))
            adds.append(op)
        elif kind == "hold_segment":
            quote = (op.get("quote") or "").strip()
            if not is_valid_quote(quote, text):
                continue
            holds.append({"quote": quote, "topic": op.get("topic")})

    return adds, holds
