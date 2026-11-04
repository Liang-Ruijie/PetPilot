from app.services.model_client import ModelClient


def test_reattribute_after_pet_created(client, auth, monkeypatch):
    # 未建猫时发“明月今天吃了26克” → 挂起
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "add_observation", "quote": "明月今天吃了26克", "pet_id": 1, "topic": "进食", "value": 26, "unit": "克"}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", json={"text": "明月今天吃了26克"}, headers=auth)
    assert len(r.json()["held_segments"]) == 1

    # 建猫“明月” → 自动补归属
    r = client.post("/api/pets", json={"name": "明月"}, headers=auth)
    assert r.status_code == 201

    facts = client.get("/api/facts", headers=auth).json()["facts"]
    assert len(facts) == 1
    assert facts[0]["pet_name"] == "明月"
    assert facts[0]["value"] == 26.0

    held = client.get("/api/held", headers=auth).json()["held_segments"]
    assert len(held) == 0  # 挂起已解决


def test_photo_description_becomes_fact(client, auth):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    r = client.post(
        "/api/photos",
        files={"file": ("cat.png", png, "image/png")},
        data={"description": "明月拉稀了", "pet_id": "1"},
        headers=auth,
    )
    assert r.status_code == 201
    facts = client.get("/api/facts", headers=auth).json()["facts"]
    assert any(f["topic"] == "照片记录" and f["quote"] == "明月拉稀了" for f in facts)


def test_reminder_fill_time(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"reminders": [{"pet_id": 1, "quote": "明天提醒我给明月称重"}]},
        },
    )
    r = client.post("/api/messages", json={"text": "明天提醒我给明月称重"}, headers=auth)
    rid = r.json()["reminders"][0]["id"]
    assert r.json()["reminders"][0]["due_at"] is None  # 无具体时间 → 待补

    r = client.post(f"/api/reminders/{rid}/update", json={"due_at": "明天上午九点"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["due_at"] is not None


def test_reminder_without_cat_not_attributed(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"reminders": [{"pet_id": 1, "quote": "明天提醒称重"}]},
        },
    )
    r = client.post("/api/messages", json={"text": "明天提醒称重"}, headers=auth)
    data = r.json()
    assert len(data["reminders"]) == 1
    assert data["reminders"][0]["pet_name"] is None  # 未指定猫，不猜


def test_resolve_held_by_clarification(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)

    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "hold_segment", "quote": "他今天拉稀了", "topic": "状态"}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", json={"text": "他今天拉稀了，状态不好"}, headers=auth)
    held_id = r.json()["held_segments"][0]["id"]

    # 主人澄清“他指的是明月”
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [{"kind": "resolve_held", "held_id": held_id, "pet_id": 1, "quote": "他指的是明月"}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", json={"text": "他指的是明月"}, headers=auth)
    data = r.json()
    assert any(f["pet_name"] == "明月" and f["topic"] == "状态" for f in data["facts"])
    assert client.get("/api/held", headers=auth).json()["held_segments"] == []


def test_clarification_assigns_pending_reminder(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)

    # “明天称体重” → 提醒，待补对象
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {
            "operations": [],
            "dialogue": {"reminders": [{"pet_id": 1, "quote": "明天称体重"}]},
        },
    )
    r = client.post("/api/messages", json={"text": "明天称体重"}, headers=auth)
    assert r.json()["reminders"][0]["pet_name"] is None

    # 澄清“他是明月” → 待补对象的提醒归到明月
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None: {"operations": [], "dialogue": {}},
    )
    client.post("/api/messages", json={"text": "他是明月"}, headers=auth)
    reminders = client.get("/api/reminders", headers=auth).json()["reminders"]
    assert reminders[0]["pet_name"] == "明月"
