import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def _ensure_dir(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)


_ensure_dir(settings.database_url)

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)
