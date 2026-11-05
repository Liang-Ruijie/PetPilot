from app.services.model_client import ModelClient


def test_weekly_review_generated(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0, history=None: {
            "operations": [{"kind": "add_observation", "quote": "明月今天吃了20克", "pet_id": 1, "topic": "进食", "value": 20, "unit": "克"}],
            "dialogue": {},
        },
    )
    client.post("/api/messages", data={"text": "明月今天吃了20克"}, headers=auth)
    r = client.post("/api/weekly-review", json={}, headers=auth)
    assert r.status_code == 201
    assert "mock" in r.json()["summary"]


def test_weekly_review_empty(client, auth):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    r = client.post("/api/weekly-review", json={}, headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WEEKLY_EMPTY"


def test_weekly_review_includes_photos(client, auth):
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    r = client.post(
        "/api/photos",
        files={"file": ("cat.png", png, "image/png")},
        data={"description": "贝塔吐毛球", "pet_id": "1"},
        headers=auth,
    )
    assert r.status_code == 201
    # 只有照片、没有文字事实，也能生成周回顾，且包含照片描述
    r = client.post("/api/weekly-review", json={}, headers=auth)
    assert r.status_code == 201
    assert "吐毛球" in r.json()["summary"]
