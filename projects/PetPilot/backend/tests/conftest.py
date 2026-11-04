import os

os.environ["MODEL_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///./data/test.db"

import pytest
from fastapi.testclient import TestClient

from app.db import engine
from app.models import Base
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture()
def auth(client):
    r = client.post("/api/auth/login", json={"code": "123456"})
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}
