def test_login_ok(client):
    r = client.post("/api/auth/login", json={"code": "123456"})
    assert r.status_code == 200
    assert r.json()["token"]


def test_login_wrong_code(client):
    r = client.post("/api/auth/login", json={"code": "000"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_INVALID_CODE"
