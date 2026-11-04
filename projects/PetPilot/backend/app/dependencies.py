from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

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
