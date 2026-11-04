import json
import time

from app.config import settings
from app.schemas import RawModelOutput
from app.services.quote import strip_code_fence


class ModelError(Exception):
    """模型调用失败（网络/超时/SDK 初始化失败等）。"""


class SchemaError(Exception):
    """模型输出不是合法 JSON 或结构不合法。"""


SYSTEM_PROMPT = """你是宠物合伙人 Personal Agent，服务猫主人的持续助理。把主人消息拆成增量操作，严格按 Schema 输出 JSON（只输出 JSON 对象，不要 markdown 代码块）。

铁律：
0. op_id 从 a 开始递增；start/end 是 quote 在原文中的起止位置，不确定可写 0。
1. pet_id 只能是「允许的宠物身份」里列出的 ID；不在列表或无法确认归属时，用 hold_segment 挂起（quote 保留原文），reason 写「归属未知」。不得编造 pet_id、不得留空、不得猜成当前宠物。
2. 明确出现多只猫时拆成多个片段，各归各主；只有无法归属的片段才挂起。
3. 极性 polarity 表示主题的陈述状态，不是情绪好坏：「没精神」=状态+negative；「没有呕吐」=呕吐+negative；「大约吃了一半」保留近似表达，不编造克数。
4. quantity_scope 按原文动词判断：吃/喝/摄→intake，放/给/倒/盛→provided；数量或单位缺失时留空，不因缺数量改类型。
5. 结构化字段能确定才填，不擅自补全：
   - value/unit：数值与单位（克/g/kg）
   - historical_current：「以前100克」=historical，「今天20克」=current
   - occurred_at：有明确日期才填（YYYY-MM-DD）；「今天」由程序换算，你省略不填
   - change_kind 固定 new
6. quote 从明确宠物名字开始、保留到该片段结束的连续原文，不拼接、不改写。
7. 问候、能力咨询、澄清可以输出空 operations，同时用 dialogue.answer 自然回答；含观察信息的输入必须给操作，不能用回答代替归档。
8. 你不得写「已保存/已记录/已整理」等动作结果——成功结果由服务器验证后另行反馈。
9. 一票阻断红线：跨猫泄露、编造数值、假保存、药量自主建议。"""


class ModelClient:
    def __init__(self):
        self.client = None
        if settings.model_api_key:
            import openai

            self.client = openai.OpenAI(
                api_key=settings.model_api_key,
                base_url=settings.model_base_url,
                timeout=settings.model_timeout,
                max_retries=1,
            )

    @staticmethod
    def _build_user(text: str, pets) -> str:
        lines = []
        if pets:
            lines.append("允许的宠物身份：")
            for p in pets:
                lines.append(f"- ID {p.id}：{p.name}")
        else:
            lines.append("允许的宠物身份：（空）")
        lines.append("")
        lines.append(f"主人消息：{text}")
        return "\n".join(lines)

    def extract(self, text: str, pets) -> dict:
        if self.client is None:
            return self._mock(text)

        user_msg = self._build_user(text, pets)
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                resp = self.client.chat.completions.create(
                    model=settings.model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = (resp.choices[0].message.content or "").strip()
                data = json.loads(strip_code_fence(content))
                validated = RawModelOutput.model_validate(data)
                return {
                    "operations": validated.operations,
                    "dialogue": validated.dialogue,
                }
            except (json.JSONDecodeError, ValueError) as e:
                last_err = SchemaError("模型输出不是合法 JSON 或结构不合法")
            except Exception as e:  # SDK 初始化失败、超时、限流等
                last_err = ModelError(f"模型调用失败：{e}")
            if attempt == 0:
                time.sleep(0.5)

        if isinstance(last_err, SchemaError):
            raise last_err
        raise ModelError(str(last_err) if last_err else "模型调用失败")

    @staticmethod
    def _mock(text: str) -> dict:
        return {
            "operations": [],
            "dialogue": {
                "answer": {
                    "kind": "conversation",
                    "text": "（mock 模式）真实模型接入后会自动分猫归档。",
                }
            },
        }
