from app.services.model_client import ModelClient, ModelError


def _add(op_id="a", pet_id=1, topic="进食", value=26, unit="克", quote="明月今天吃了26克"):
    return {
        "kind": "add_observation",
        "op_id": op_id,
        "quote": quote,
        "pet_id": pet_id,
        "topic": topic,
        "value": value,
        "unit": unit,
        "quantity_scope": "intake",
        "historical_current": "current",
        "change_kind": "new",
    }


def _hold(op_id="a", quote="贝塔2有点拉稀", topic="状态"):
    return {"kind": "hold_segment", "op_id": op_id, "quote": quote, "topic": topic, "reason": "归属未知"}


def test_single_attribution(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)
    text = "明月今天吃了26克"
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0: {"operations": [_add(pet_id=1, quote=text)], "dialogue": {}},
    )
    r = client.post("/api/messages", data={"text": text}, headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert len(data["facts"]) == 1
    assert data["facts"][0]["pet_name"] == "明月"
    assert "已保存" in data["receipt"]


def test_multi_pet_split(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)
    text = "明月今天吃了26克，贝塔有点拉稀"
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0: {
            "operations": [
                _add("a", 1, "进食", 26, "克", "明月今天吃了26克"),
                _add("b", 2, "状态", None, None, "贝塔有点拉稀"),
            ],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", data={"text": text}, headers=auth)
    data = r.json()
    assert len(data["facts"]) == 2
    assert {f["pet_name"] for f in data["facts"]} == {"明月", "贝塔"}


def test_invalid_pet_id_reattributed(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    text = "明月今天吃了26克"
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0: {"operations": [_add(pet_id=999, quote=text)], "dialogue": {}},
    )
    r = client.post("/api/messages", data={"text": text}, headers=auth)
    data = r.json()
    assert len(data["facts"]) == 1
    assert data["facts"][0]["pet_name"] == "明月"


def test_hold_segment(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)
    text = "贝塔2有点拉稀"
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0: {"operations": [_hold(quote=text)], "dialogue": {}},
    )
    r = client.post("/api/messages", data={"text": text}, headers=auth)
    data = r.json()
    assert len(data["facts"]) == 0
    assert len(data["held_segments"]) == 1


def test_near_miss_name_held(client, auth, monkeypatch):
    # 模型错误地把“贝塔2”子串匹配到“贝塔”，服务端应挂起而不是归档
    client.post("/api/pets", json={"name": "贝塔"}, headers=auth)
    text = "贝塔2 有点拉稀"
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0: {
            "operations": [{"kind": "add_observation", "quote": text, "pet_id": 1, "topic": "状态"}],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", data={"text": text}, headers=auth)
    data = r.json()
    assert len(data["facts"]) == 0
    assert len(data["held_segments"]) == 1


def test_quote_invalid_dropped(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    text = "明月今天吃了26克"
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0: {"operations": [_add(quote="不是原文的内容")], "dialogue": {}},
    )
    r = client.post("/api/messages", data={"text": text}, headers=auth)
    data = r.json()
    assert len(data["facts"]) == 0


def test_model_failure_no_fake_save(client, auth, monkeypatch):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)

    def boom(self, text, pets, facts=None, held=None, photo_count=0):
        raise ModelError("超时")

    monkeypatch.setattr(ModelClient, "extract", boom)
    r = client.post("/api/messages", data={"text": "明月今天吃了26克"}, headers=auth)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "MODEL_FAILED"
    # 不假保存：没有任何消息被写库
    assert client.get("/api/messages", headers=auth).json()["messages"] == []


def test_occurred_at_defaults_today(client, auth, monkeypatch):
    from datetime import date

    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    text = "明月今天吃了26克"
    monkeypatch.setattr(
        ModelClient, "extract",
        lambda self, t, pets, facts=None, held=None, photo_count=0: {
            "operations": [
                {"kind": "add_observation", "quote": text, "pet_id": 1, "topic": "进食", "value": 26, "unit": "克"}
            ],
            "dialogue": {},
        },
    )
    r = client.post("/api/messages", data={"text": text}, headers=auth)
    assert r.status_code == 200
    # 通过 /facts 验证 occurred_at 被设为当天
    f = client.get("/api/facts", headers=auth).json()["facts"]
    assert len(f) == 1
