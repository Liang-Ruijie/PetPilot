import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models import Session as AuthSession
from app.schemas import LoginRequest, LoginResponse

router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    if body.code != settings.fixed_login_code:
        raise HTTPException(
            401, detail={"error": {"code": "AUTH_INVALID_CODE", "message": "验证码错误"}}
        )
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token=token))
    db.commit()
    return {"token": token}
