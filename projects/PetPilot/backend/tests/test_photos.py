PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def test_photo_upload_ok(client, auth):
    r = client.post(
        "/api/photos",
        files={"file": ("cat.png", PNG_HEAD, "image/png")},
        data={"description": "贝塔的照片"},
        headers=auth,
    )
    assert r.status_code == 201
    assert r.json()["description"] == "贝塔的照片"


def test_photo_invalid_type(client, auth):
    r = client.post(
        "/api/photos",
        files={"file": ("evil.txt", b"hello world", "text/plain")},
        headers=auth,
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "FILE_TYPE_INVALID"
