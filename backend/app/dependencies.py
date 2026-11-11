from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Session as AuthSession


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_session(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthSession:
    """本地开发期的 Bearer 会话检查（固定验证码登录）。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            401, detail={"error": {"code": "AUTH_REQUIRED", "message": "请先登录"}}
        )
    token = authorization[len("Bearer "):]
    s = db.query(AuthSession).filter(AuthSession.token == token).first()
    if not s:
        raise HTTPException(
            401, detail={"error": {"code": "AUTH_REQUIRED", "message": "登录已失效"}}
        )
    return s


def get_owner_id(request: Request) -> str:
    """当前用户标签（owner_id）。本地模式固定 "local"；线上（require_login=1）从 Cookie 读会话。"""
    if not settings.require_login:
        return "local"
    from app.services.auth import SESSION_COOKIE, read_session
    token = request.cookies.get(SESSION_COOKIE)
    label = read_session(settings, token)
    if label is None:
        raise HTTPException(
            401, detail={"error": {"code": "UNAUTHORIZED", "message": "请先登录"}}
        )
    return label
