from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.dependencies import get_owner_id
from app.services.asr_client import AsrError, flash_transcribe

router = APIRouter()

_MAX_WAV = 44 + 16000 * 60 * 2  # 最多 60 秒的 16k/16bit 单声道 wav


@router.post("/asr")
async def transcribe(request: Request, sess=Depends(get_owner_id)):
    """语音转文字：接收 audio/wav，调腾讯云 Flash ASR，返回文本。"""
    content_type = request.headers.get("content-type", "")
    if "audio/wav" not in content_type:
        raise HTTPException(
            415, detail={"error": {"code": "ASR_AUDIO", "message": "请使用录音入口"}}
        )
    audio = await request.body()
    if not audio or len(audio) > _MAX_WAV:
        raise HTTPException(
            413, detail={"error": {"code": "ASR_AUDIO", "message": "录音为空或过长，请分成短句重录"}}
        )
    try:
        text = flash_transcribe(settings.asr_app_id, settings.asr_secret_id, settings.asr_secret_key, audio)
    except AsrError as e:
        raise HTTPException(e.status, detail={"error": {"code": e.code, "message": e.message}})
    return {"text": text}
