"""照片文件存储：格式/真实类型/大小/安全文件名校验；只存原图，不做 OCR。"""
import os
import uuid

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_SIZE = 5 * 1024 * 1024  # 5MB

_MAGIC = {
    b"\xff\xd8\xff": ".jpg",       # JPEG
    b"\x89PNG\r\n\x1a\n": ".png",  # PNG
    b"RIFF": ".webp",              # WEBP（再确认 WEBP 标记）
}


def _real_ext(head: bytes) -> str | None:
    for magic, ext in _MAGIC.items():
        if head.startswith(magic):
            if ext == ".webp" and b"WEBP" not in head[:12]:
                continue
            return ext
    return None


def validate_image(content: bytes, original_name: str) -> str | None:
    """返回错误信息；None 表示通过。"""
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXT:
        return "不支持的图片格式（只支持 jpg/png/webp）"
    if len(content) > MAX_SIZE:
        return "图片超过 5MB 上限"
    if _real_ext(content[:16]) is None:
        return "文件内容不是有效图片"
    return None


def save_image(content: bytes, original_name: str, uploads_dir: str) -> tuple[str, str]:
    """返回 (安全文件名, 存储路径)。"""
    ext = os.path.splitext(original_name)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(uploads_dir, exist_ok=True)
    path = os.path.join(uploads_dir, safe_name)
    with open(path, "wb") as f:
        f.write(content)
    return safe_name, path
