def test_create_and_list_pet(client, auth):
    r = client.post("/api/pets", json={"name": "明月"}, headers=auth)
    assert r.status_code == 201
    assert r.json()["name"] == "明月"
    r = client.get("/api/pets", headers=auth)
    assert r.json()["pets"] == [{"id": 1, "name": "明月"}]


def test_duplicate_pet(client, auth):
    client.post("/api/pets", json={"name": "明月"}, headers=auth)
    r = client.post("/api/pets", json={"name": "明月"}, headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PET_NAME_DUPLICATE"


def test_pets_require_auth(client):
    r = client.get("/api/pets")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"
