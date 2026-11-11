"""腾讯云 ASR「Flash 识别」客户端（语音转文字）。

复用项目 2（AI-Work）的对接方式：
- 接口：https://asr.cloud.tencent.com/asr/flash/v1/{appId}
- 签名：HMAC-SHA1(secretKey, 'POST' + canonical)，canonical 用原始值、URL 用 urlencode 后的值
- 入参：16k 中文、wav、单声道；响应 flash_result 取 channel_id=0 的 text
"""
import base64
import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx


class AsrError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status


def _sign(secret_key: str, canonical: str) -> str:
    digest = hmac.new(secret_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def flash_transcribe(app_id: str, secret_id: str, secret_key: str, audio: bytes, timeout: float = 25.0) -> str:
    """上传 wav 音频，返回识别文本。失败抛 AsrError。"""
    if not app_id or not secret_id or not secret_key:
        raise AsrError("ASR_CONFIG", "语音转写尚未配置", 503)
    values = {
        "customization_id": "",
        "reinforce_hotword": "0",
        "sentence_max_length": "0",
        "convert_num_mode": "0",
        "engine_type": "16k_zh",
        "filter_dirty": "0",
        "filter_modal": "0",
        "filter_punc": "0",
        "first_channel_only": "1",
        "secretid": secret_id,
        "speaker_diarization": "0",
        "timestamp": str(int(time.time())),
        "voice_format": "wav",
        "word_info": "0",
    }
    entries = sorted(values.items())
    target = f"asr.cloud.tencent.com/asr/flash/v1/{app_id}"
    canonical = target + "?" + "&".join(f"{k}={v}" for k, v in entries)
    url = "https://" + target + "?" + urlencode(entries)
    authorization = _sign(secret_key, "POST" + canonical)

    try:
        resp = httpx.post(
            url,
            headers={
                "Host": "asr.cloud.tencent.com",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(audio)),
                "Authorization": authorization,
            },
            content=audio,
            timeout=timeout,
        )
    except httpx.HTTPError:
        raise AsrError("ASR_HTTP", "语音服务未正常响应，请稍后重试", 502)

    try:
        data = resp.json()
    except ValueError:
        raise AsrError("ASR_RESPONSE", "语音服务返回格式异常，请稍后重试", 502)

    if data.get("code") != 0:
        code = data.get("code")
        if code in (4004, 4005):
            raise AsrError("ASR_QUOTA", "免费语音额度不可用，请继续输入文字", 403)
        if code == 4002:
            raise AsrError("ASR_AUTH", "语音服务鉴权失败，请检查密钥", 502)
        raise AsrError("ASR_PROVIDER", "本段语音未能转写，请继续输入文字", 502)

    text = ""
    for v in data.get("flash_result") or []:
        if v.get("channel_id") == 0:
            text = (v.get("text") or "").strip()
            break
    if not text:
        raise AsrError("ASR_EMPTY", "没有识别到有效文字，请重新录音或输入文字", 422)
    return text
