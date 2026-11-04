import pytest


@pytest.mark.django_db
def test_index_and_healthz(client):
    assert client.get("/").status_code == 200
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert client.get("/api/v1/").status_code == 401  # cần đăng nhập
