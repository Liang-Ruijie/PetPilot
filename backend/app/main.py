import os

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import asr, auth, care, facts, messages, pets, photos, reminders, weekly

app = FastAPI(title="PetPilot")

app.include_router(auth.router, prefix="/api")
app.include_router(pets.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(facts.router, prefix="/api")
app.include_router(reminders.router, prefix="/api")
app.include_router(photos.router, prefix="/api")
app.include_router(care.router, prefix="/api")
app.include_router(weekly.router, prefix="/api")
app.include_router(asr.router, prefix="/api")


@app.exception_handler(HTTPException)
async def http_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数不合法"}},
    )


_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(_static_dir, "index.html"))
