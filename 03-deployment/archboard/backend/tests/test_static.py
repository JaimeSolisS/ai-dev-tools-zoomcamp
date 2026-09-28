from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def static_client(make_app, tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>shell</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    with TestClient(make_app(static_dir=str(dist))) as c:
        yield c


def test_serves_index_at_root(static_client):
    r = static_client.get("/")
    assert r.status_code == 200
    assert "shell" in r.text


def test_serves_assets(static_client):
    r = static_client.get("/assets/app.js")
    assert r.status_code == 200
    assert r.text == "console.log(1)"


def test_client_routes_get_the_app_shell(static_client):
    r = static_client.get("/sessions/abc")
    assert r.status_code == 200
    assert "shell" in r.text


def test_api_still_wins_and_unknown_api_paths_are_404(static_client):
    assert static_client.get("/v1/auth/me").status_code == 401
    assert static_client.get("/v1/nope").status_code == 404
    assert static_client.get("/openapi.json").status_code == 200


def test_does_not_escape_the_static_folder(static_client):
    r = static_client.get("/..%2Fsecret.txt")
    assert "nope" not in r.text
