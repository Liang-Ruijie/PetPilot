"""就医准备摘要生成（只生成，不外发）。"""
from app.config import settings
from app.services.model_client import ModelClient

SUMMARY_PROMPT = """你是宠物合伙人 Personal Agent。把下面关于同一只猫的观察记录整理成一段「就医准备摘要」，用中文、按时间顺序陈述事实。

要求：
1. 只陈述记录里已有的事实，不编造数值、不补充记录里没有的症状；
2. 不诊断、不处方、不写「建议服用/剂量/确诊/治愈」等；
3. 用主人能直接念给医生听的平实语言，长度 100~200 字；
4. 直接输出摘要正文，不要标题、不要解释。"""


def generate_care_summary(pet_name: str, facts: list) -> str:
    return _generate(SUMMARY_PROMPT, f"宠物：{pet_name}", facts, pet_name)


WEEKLY_PROMPT = """你是宠物合伙人 Personal Agent。把下面这些关于猫的近 7 天观察记录整理成一段「周回顾」，用中文、按时间顺序。

要求：
1. 只陈述记录里已有的事实，不编造数值、不补充记录里没有的症状；
2. 区分「日常正常记录」与「值得关注的变化」，语气客观；
3. 不诊断、不处方、不写「建议服用/剂量/确诊/治愈」；
4. 直接输出正文，100~200 字。"""


def generate_weekly_review(pet_label: str, facts: list) -> str:
    return _generate(WEEKLY_PROMPT, f"猫：{pet_label}", facts, pet_label)


def _generate(prompt: str, label: str, facts: list, mock_name: str) -> str:
    if not facts:
        return ""
    lines = []
    for f in facts:
        v = f"{f.value}{f.unit or ''}" if f.value is not None else ""
        lines.append(f"- {f.topic or '记录'} {v}（{f.quote}）".strip())
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
