from app.services.model_client import ModelClient


def test_correction_updates_same_fact(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "add_observation", "quote": "明月今天吃了20克", "pet_id": 1, "topic": "进食", "value": 20, "unit": "克"}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", json={"text": "明月今天吃了20克"}, headers=auth)
    fact_id = r.json()["facts"][0]["id"]

    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "correct_fact", "quote": "明月是40克，不是20克", "fact_id": fact_id, "expected_version": 1, "value": 40, "unit": "克"}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", json={"text": "明月是40克，不是20克"}, headers=auth)
    data = r.json()
    assert len(data["corrections"]) == 1
    assert data["corrections"][0]["status"] == "ok"
    assert data["corrections"][0]["version"] == 2

    facts = client.get("/api/facts", headers=auth).json()["facts"]
    assert len(facts) == 1  # 不新增一条
    assert facts[0]["value"] == 40.0
    assert facts[0]["version"] == 2


def test_correction_version_conflict_no_change(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "add_observation", "quote": "明月今天吃了20克", "pet_id": 1, "topic": "进食", "value": 20, "unit": "克"}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", json={"text": "明月今天吃了20克"}, headers=auth)
    fact_id = r.json()["facts"][0]["id"]

    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "correct_fact", "quote": "明月是40克", "fact_id": fact_id, "expected_version": 99, "value": 40}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", json={"text": "明月是40克"}, headers=auth)
    data = r.json()
    assert data["corrections"][0]["status"] == "conflict"
    facts = client.get("/api/facts", headers=auth).json()["facts"]
    assert facts[0]["value"] == 20.0  # 未改动


def test_reminder_authorized(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"reminders": [{"pet_id": 1, "quote": "明天上午九点提醒我给明月称重"}]},
        },
    )
    r = client.post("/api/messages", json={"text": "明天上午九点提醒我给明月称重"}, headers=auth)
    data = r.json()
    assert len(data["reminders"]) == 1
    assert data["reminders"][0]["due_at"] is not None


def test_reminder_negation_rejected(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"reminders": [{"pet_id": 1, "quote": "别提醒我称重"}]},
        },
    )
    r = client.post("/api/messages", json={"text": "别提醒我称重"}, headers=auth)
    assert len(r.json()["reminders"]) == 0


def test_reminder_conditional_rejected(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"reminders": [{"pet_id": 1, "quote": "如果明天天气好提醒我"}]},
        },
    )
    r = client.post("/api/messages", json={"text": "如果明天天气好提醒我"}, headers=auth)
    assert len(r.json()["reminders"]) == 0


def test_reminder_transitions(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"reminders": [{"pet_id": 1, "quote": "明天上午九点提醒我给明月称重"}]},
        },
    )
    r = client.post("/api/messages", json={"text": "明天上午九点提醒我给明月称重"}, headers=auth)
    rid = r.json()["reminders"][0]["id"]

    r = client.post(f"/api/reminders/{rid}/complete", headers=auth)
    assert r.json()["status"] == "done"
    r = client.post(f"/api/reminders/{rid}/pause", headers=auth)
    assert r.json()["status"] == "paused"
    r = client.post(f"/api/reminders/{rid}/cancel", headers=auth)
    assert r.json()["status"] == "cancelled"


def test_care_summary_generated_and_simulated_reply(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "add_observation", "quote": "贝塔有点拉稀", "pet_id": 1, "topic": "状态"}],
            "dialogue": {},
        },
    )
    client.post("/api/messages", json={"text": "贝塔有点拉稀"}, headers=auth)

    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"care_requests": [{"pet_id": 1, "quote": "帮我整理贝塔的就医摘要，先不要发", "title": "贝塔就医准备", "fact_ids": []}]},
        },
    )
    r = client.post("/api/messages", json={"text": "帮我整理贝塔的就医摘要，先不要发"}, headers=auth)
    data = r.json()
    assert len(data["care_requests"]) == 1
    assert "贝塔" in data["care_requests"][0]["summary"]

    sid = data["care_requests"][0]["id"]
    r2 = client.post(f"/api/care-summaries/{sid}/simulate-reply", headers=auth)
    assert r2.json()["is_simulated"] is True
    assert "模拟" in r2.json()["reply"]
