"""提醒授权裁决 + 中文时间解析（服务端确定性逻辑，不交给模型）。"""
import re
from datetime import datetime, timedelta

NEGATION = ["别提醒", "不用提醒", "不要提醒", "别再提醒", "不提醒", "取消提醒", "别叫我提醒", "别让我提醒"]
CONDITIONAL = ["如果", "假如", "要是", "万一"]
REFERENCE = ["医生说", "他说", "她说", "大夫说"]
# 否定词 + 动作词：只要“别/不要/不用/不”后面同一小句里出现这些动作，就视为否定（如“别在明天上午九点提醒我给明月称重”）
NEG_WORDS = ["别", "不要", "不用", "不需", "不"]
ACTION_WORDS = ["提醒", "称重", "打针", "喂", "吃药", "记录", "设置", "设定", "叫"]


def is_authorized_reminder(quote: str) -> bool:
    """否定/假设/问句/引用他人 → 不算授权，不建提醒。"""
    q = quote or ""
    for m in NEGATION + CONDITIONAL + REFERENCE:
        if m in q:
            return False
    if q.strip().endswith("？") or q.strip().endswith("?") or "吗" in q:
        return False
    # 增强：否定词后面的同一小句里出现动作词，也视为否定（覆盖“别在…提醒…”这类隔字否定）
    for neg in NEG_WORDS:
        idx = q.find(neg)
        while idx >= 0:
            rest = q[idx + len(neg):]
            seg = re.split(r"[，。！？；,.;?!\s]", rest)[0]
            # “不指定/不确定猫名”否定的是归属，不是设置提醒。
            # 单字“设/定”只作为否定后直接出现的动作，不能命中“指定”的尾字。
            if any(a in seg for a in ACTION_WORDS) or seg.startswith(("设", "定")):
                return False
            idx = q.find(neg, idx + 1)
    return True


_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_to_int(s: str) -> int | None:
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in _CN:
        return _CN[s]
    if "十" in s:
        parts = s.split("十")
        tens = _CN.get(parts[0], 1) if parts[0] else 1
        ones = _CN.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    return None


def parse_due_time(quote: str) -> datetime | None:
    """解析常见中文时间表达：今天/明天/后天 + 上午/下午/晚上 + X点(半/X分)。
    分钟必须紧跟“点”后（如“九点四十五分”），不能把“玩二十分钟”这类持续时间当分钟。"""
    q = quote or ""
    day_offset = 0
    if "后天" in q:
        day_offset = 2
    elif "明天" in q:
        day_offset = 1
    elif "今天" in q:
        day_offset = 0

    m = re.search(
        r"(上午|下午|晚上|中午|早上|早晨)?\s*([0-9]+|[一二两三四五六七八九十]+)\s*点(?:半)?(?:\s*([0-9]+|[一二两三四五六七八九十]+)\s*分)?",
        q,
    )
    if not m:
        return None
    period = m.group(1)
    hour = _cn_to_int(m.group(2))
    if hour is None or not (0 <= hour <= 23):
        return None
    minute = 0
    if "半" in m.group(0):
        minute = 30
    elif m.group(3):
        minute = _cn_to_int(m.group(3)) or 0
        if not (0 <= minute <= 59):
            minute = 0
    if period in ("下午", "晚上", "中午") and hour < 12:
        hour += 12
    now = datetime.now()
    due = (now + timedelta(days=day_offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return due
