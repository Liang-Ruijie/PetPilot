from app.services.model_client import ModelClient


def test_weekly_review_generated(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None: {
            "operations": [{"kind": "add_observation", "quote": "明月今天吃了20克", "pet_id": 1, "topic": "进食", "value": 20, "unit": "克"}],
            "dialogue": {},
        },
    )
    client.post("/api/messages", json={"text": "明月今天吃了20克"}, headers=auth)
    r = client.post("/api/weekly-review", json={}, headers=auth)
    assert r.status_code == 201
    assert "mock" in r.json()["summary"]


def test_weekly_review_empty(client, auth):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    r = client.post("/api/weekly-review", json={}, headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WEEKLY_EMPTY"
