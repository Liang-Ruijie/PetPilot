import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models import Session as AuthSession
from app.schemas import LoginRequest, LoginResponse
from app.services.auth import (
    SESSION_COOKIE,
    client_ip,
    login_limiter,
    make_session,
    match_invite_code,
    proxied_client_ip,
)

router = APIRouter()


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    # 本地（未开启 require_login）：固定验证码 + Bearer token（维持既有验收方式）
    if not settings.require_login:
        if body.code != settings.fixed_login_code:
            raise HTTPException(
                401, detail={"error": {"code": "AUTH_INVALID_CODE", "message": "验证码错误"}}
            )
        token = secrets.token_urlsafe(32)
        db.add(AuthSession(token=token))
        db.commit()
        return LoginResponse(token=token)

    # 线上（require_login=1）：邀请码 + HttpOnly Cookie 会话
    if not settings.invite_codes_map or not settings.session_secret:
        raise HTTPException(
            503, detail={"error": {"code": "AUTH_NOT_CONFIGURED", "message": "登录功能还没配置好"}}
        )
    ip = client_ip(
        settings,
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        request.headers.get(settings.client_ip_header) if settings.client_ip_header else None,
        proxied_client_ip(settings, request.headers.get("x-proxy-secret"), request.headers.get("x-client-ip")),
    )
    left = login_limiter.locked_seconds_left(ip)
    if left:
        raise HTTPException(
            429, detail={"error": {"code": "LOGIN_LOCKED", "message": f"输错次数太多，请 {max(1, (left + 59) // 60)} 分钟后再试"}}
        )
    label = match_invite_code(settings, body.code.strip())
    if label is None:
        remaining = login_limiter.record_failure(ip)
        if remaining == 0:
            raise HTTPException(
                429, detail={"error": {"code": "LOGIN_LOCKED", "message": "输错次数太多，请 15 分钟后再试"}}
            )
        raise HTTPException(
            401, detail={"error": {"code": "INVALID_CODE", "message": f"邀请码不对，还可以再试 {remaining} 次"}}
        )
    login_limiter.record_success(ip)
    # demo 空间每次登录自动重置成预置测试数据
    if label == settings.demo_label:
        from app.services.demo_seed import reset_demo
        reset_demo()
    response.set_cookie(
        SESSION_COOKIE,
        make_session(settings, label, body.code.strip()),
        max_age=settings.session_max_age_seconds,
        path="/",
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return LoginResponse(token="", label=label)


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"ok": True}
