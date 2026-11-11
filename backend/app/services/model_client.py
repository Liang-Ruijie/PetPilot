import json
import time

from app.config import settings
from app.schemas import RawModelOutput
from app.services.quote import strip_code_fence


class ModelError(Exception):
    """模型调用失败（网络/超时/SDK 初始化失败等）。"""


class SchemaError(Exception):
    """模型输出不是合法 JSON 或结构不合法。"""


SYSTEM_PROMPT = """你是PetPilot Personal Agent，服务猫主人的持续助理。把主人消息拆成增量操作，严格按 Schema 输出 JSON（只输出 JSON 对象，不要 markdown 代码块）。

## 输出 Schema

operations 数组（每个 operation 必须是对象，必须带 kind 字段）：
kind 有四种取值：
- add_observation：新增观察（归档到某只猫），字段：kind, op_id, quote, pet_id, topic, value, unit, quantity_scope, historical_current, occurred_at, polarity, change_kind
- correct_fact：纠错（更新已有事实），字段：kind, op_id, quote, fact_id, expected_version, pet_id, topic, value, unit
- hold_segment：归属未知挂起，字段：kind, op_id, quote, reason, topic, value, unit, quantity_scope, historical_current, polarity（保留原文已明确的数值/单位等信息，供补归属时重建）
- resolve_held：主人澄清了之前挂起片段的归属（如「他指的是明月」），字段：kind, op_id, quote, held_id, pet_id；held_id 从「待归属片段」列表里选，pet_id 是被澄清的那只猫

dialogue 对象（可选字段）：
- answer：自然回答（对象 {"text":"..."} 或字符串）
- explanation：带引用的短解释（对象 {"text":"..."} 或字符串）
- reminders：主人本轮明确交代的提醒，数组，每项 {"pet_id": 猫ID, "quote": 完整原话子句}
- care_requests：主人要求整理就医摘要，数组，每项 {"pet_id": 猫ID, "quote": 完整原话, "title": 标题, "fact_ids": [事实ID]}

正确示例（主人消息“明月今天吃了26克，贝塔有点拉稀”）：
{"operations":[{"kind":"add_observation","op_id":"a","quote":"明月今天吃了26克","pet_id":1,"topic":"进食","value":26,"unit":"克","quantity_scope":"intake","historical_current":"current","change_kind":"new"},{"kind":"add_observation","op_id":"b","quote":"贝塔有点拉稀","pet_id":2,"topic":"状态","polarity":"negative","change_kind":"new"}],"dialogue":{"answer":{"text":"收到，已分别记到明月和贝塔。"}}}
禁止：把 observation 写成没有 kind 的对象；禁止用 hold_segment 承载已明确归属的片段。

## 铁律
0. op_id 从 a 开始递增。
1. pet_id 只能是「允许的宠物身份」里列出的 ID；不在列表或无法确认归属时用 hold_segment 挂起（reason 写「归属未知」）。不得编造 pet_id、不得留空、不得猜成当前宠物。
2. 明确出现多只猫时拆成多个片段，各归各主；只有无法归属的片段才挂起。
3. 极性 polarity 表示主题的陈述状态，不是情绪好坏：「没精神」=状态+negative；「没有呕吐」=呕吐+negative。
4. quantity_scope 按原文动词判断：吃/喝/摄→intake，放/给/倒/盛→provided；缺失留空。
5. 结构化字段能确定才填：value/unit 数值单位；historical_current「以前100克」=historical「今天20克」=current；occurred_at 有明确日期才填；change_kind 固定 new。
6. 纠错（correct_fact）：目标唯一才输出，引用 fact_id + expected_version（从「最近记录」里找），quote 从明确宠物名字开始连续引用到新值，不拼接不改写；歧义用 hold_segment。
7. 提醒（dialogue.reminders）：主人明确交代「提醒/几点」、或含未来时间的计划（如「明天称体重」「后天上午九点带去打针」）才输出；这类未来计划是提醒/任务，不输出 add_observation（add_observation 只用于已发生或当前状态的描述）。quote 必须是完整原话子句，不能截掉否定词；明确要求提醒但缺少具体时间或猫名时，仍必须输出 reminders，保留事项和已知猫名，缺少的猫用 null；缺时间由服务器保存为待补时间并追问，不能省略任务。否定/引用/假设/问句不算授权，不要输出 reminders。主人随后只补时间时，不重复输出 reminders，服务器会更新唯一的待补时间任务。
8. 就医准备（dialogue.care_requests）：主人要求「整理就医摘要、先不要发」才输出，fact_ids 只能引用本猫可见事实；绝不发送或选择医院。answer 里不要写摘要正文（如「【xx摘要】…」），只说“我来整理”即可，摘要正文由服务器生成后另附。
9. 照片只作为「原图+主人描述」保存，你不自动理解图片内容。
10. 你不得写「已保存/已记录/已整理/已安排/已发送」等动作结果——成功结果由服务器验证后另行反馈。
11. 一票阻断红线：跨猫泄露、编造数值、假保存、药量自主建议。
12. 当主人澄清之前挂起片段属于某只猫（如「他指的是明月」「那是贝塔的」），输出 resolve_held 引用对应的 held_id + pet_id，不要重复新建观察。
13. 追问和风险提醒只针对原文已提到的事实。**绝对禁止**输出原文没有的词汇，尤其禁止：化妆品、妊娠、肥胖、攻击、驱虫药、疫苗、绝育等与原文无关的词；只围绕原文说，宁少勿多，不确定就只确认已记录的事实。
14. 观察到健康问题（如拉稀）时，给出简短建议，并可提示「需要的话可以让我整理就医摘要」，但不要主动承诺联系医院。
15. 建猫档案请引导主人使用界面的「建猫」按钮，你无法通过对话创建猫档案；如果主人要求建猫，回复「请点右上角『建猫』按钮添加」。
16. 就医摘要只生成、不真实外发；主人说「发送/外发/发给医院」时，这是验证流程，直接给一条明确标注「模拟」的医院回复，不要说「只生成不外发」或引导点按钮。
17. 当消息带照片时，如果照片归属某只猫，在 dialogue 里输出 photo_attributions 数组：每项 {"start": 1, "end": N, "pet_id": 猫ID}，表示第 start 到第 end 张照片（含端点）归到该猫；无法确定的照片不要写进区间。
18. 最近对话历史仅供理解指代和承接上下文（如"需要"可能承接上一轮"要整理就医摘要吗"，"明月"可能回答上一轮"哪只猫"），不要据此重复执行历史中的操作；只有当前这句话明确授权，才输出对应的 add_observation / reminders / care_requests。
19. 短答只承接唯一、明确的待答事项；有多个待答事项或歧义时简短澄清，不批量执行。"好的""行""知道了"是结束语，不是授权。"""


def _parse_output(content: str, finish_reason: str | None):
    """仅容错已完整结束、且只缺最外层一个右花括号的对象。"""
    if finish_reason == "length":
        raise ValueError("模型输出被截断")
    text = strip_code_fence(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        if (finish_reason != "stop" or error.pos != len(text)
                or not text.startswith("{") or not text.endswith("}")):
            raise
        stack = []
        in_string = escaped = False
        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '\"':
                    in_string = False
            elif char == '\"':
                in_string = True
            elif char in "{[":
                stack.append(char)
            elif char in "}]":
                if not stack or stack.pop() != ("{" if char == "}" else "["):
                    raise error
        if in_string or stack != ["{"]:
            raise error
        data = json.loads(text + "}")
        if not isinstance(data, dict) or not {"operations", "dialogue"} <= data.keys():
            raise error
        return data


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
    def _build_user(text: str, pets, facts=None, held=None, photo_count=0, history=None) -> str:
        lines = []
        if photo_count:
            lines.append(f"这条消息带 {photo_count} 张照片（编号 1..{photo_count}）。")
        if history:
            lines.append("最近对话（仅供理解指代与承接，不要据此重复执行历史中的操作）：")
            for m in history:
                who = "主人" if m["role"] == "user" else "你"
                lines.append(f"- {who}：{m['content']}")
        if pets:
            lines.append("允许的宠物身份：")
            for p in pets:
                lines.append(f"- ID {p.id}：{p.name}")
        else:
            lines.append("允许的宠物身份：（空）")
        if facts:
            lines.append("")
            lines.append("最近记录（供纠错引用 fact_id/version）：")
            for f in facts:
                v = f"{f.get('value')}{f.get('unit') or ''}" if f.get("value") is not None else ""
                lines.append(
                    f"- fact_id={f['id']}, {f['pet_name']}, {f.get('topic') or '记录'} {v}, version={f['version']}, 出处={f['quote']!r}"
                )
        if held:
            lines.append("")
            lines.append("待归属片段（主人可能澄清属于哪只猫）：")
            for h in held:
                v = f"{h.get('value')}{h.get('unit') or ''}" if h.get("value") is not None else ""
                lines.append(
                    f"- held_id={h['id']}, quote={h['quote']!r}, topic={h.get('topic') or '记录'} {v}"
                )
        lines.append("")
        lines.append(f"主人消息：{text}")
        return "\n".join(lines)

    def extract(self, text: str, pets, facts=None, held=None, photo_count=0, history=None) -> dict:
        if self.client is None:
            return self._mock(text)

        user_msg = self._build_user(text, pets, facts, held, photo_count, history)
        last_err: Exception | None = None
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        for attempt in range(2):
            content = None
            try:
                resp = self.client.chat.completions.create(
                    model=settings.model_name,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = (resp.choices[0].message.content or "").strip()
                data = _parse_output(content, resp.choices[0].finish_reason)
                validated = RawModelOutput.model_validate(data)
                return {
                    "operations": validated.operations,
                    "dialogue": validated.dialogue,
                }
            except (json.JSONDecodeError, ValueError) as e:
                last_err = SchemaError("模型输出不是合法 JSON 或结构不合法")
                if attempt == 0:
                    reason = (f"JSON 格式错误：{e.msg}，位置 {e.pos}"
                              if isinstance(e, json.JSONDecodeError)
                              else "数据结构不合法或输出被截断")
                    if content:
                        messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": f"上次输出未通过校验：{reason}。请按原始输入和既定 Schema 重新输出完整 JSON 对象，不要省略括号，不要添加说明。",
                    })
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
