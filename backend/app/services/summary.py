"""就医准备摘要生成 + 周回顾生成（只生成，不外发）。"""
from app.config import settings
from app.services.model_client import ModelClient

SUMMARY_PROMPT = """你是PetPilot Personal Agent。把下面关于同一只猫的观察记录整理成一段「就医准备摘要」，用中文、按时间顺序陈述事实。

要求：
1. 只陈述记录里已有的事实，不编造数值、不补充记录里没有的症状；
2. 不诊断、不处方、不写「建议服用/剂量/确诊/治愈」等；
3. 用主人能直接念给医生听的平实语言，长度 100~200 字；
4. 直接输出摘要正文，不要标题、不要解释。"""

WEEKLY_PROMPT = """你是PetPilot Personal Agent。把下面这些关于猫的近 7 天观察记录整理成一段「周回顾」，用中文、按时间顺序。

要求：
1. 只陈述记录里已有的事实，不编造数值、不补充记录里没有的症状；
2. 区分「日常正常记录」与「值得关注的变化」，语气客观；
3. 照片只作为「原图 + 主人描述」纳入回顾，不猜测图片内容；
4. 不诊断、不处方、不写「建议服用/剂量/确诊/治愈」；
5. 直接输出正文，100~200 字。"""


def _fact_line(f) -> str:
    v = f"{f.value}{f.unit or ''}" if f.value is not None else ""
    return f"- {f.topic or '记录'} {v}（{f.quote}）".strip()


def _generate(prompt: str, label: str, lines: list[str]) -> str:
    if not lines:
        return ""
    user = f"{label}\n\n观察记录：\n" + "\n".join(lines)
    mc = ModelClient()
    if mc.client is None:
        return "【mock 模式生成】\n" + "\n".join(lines)
    resp = mc.client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def generate_care_summary(pet_name: str, facts: list) -> str:
    if not facts:
        return f"（{pet_name}暂无相关记录，无可整理的摘要。）"
    return _generate(SUMMARY_PROMPT, f"宠物：{pet_name}", [_fact_line(f) for f in facts])


def generate_weekly_review(pet_label: str, facts: list, photo_count: int = 0) -> str:
    lines = [_fact_line(f) for f in facts]
    if photo_count > 0:
        lines.append(f"- 照片：{photo_count} 张（原图已存）")
    return _generate(WEEKLY_PROMPT, f"猫：{pet_label}", lines)
