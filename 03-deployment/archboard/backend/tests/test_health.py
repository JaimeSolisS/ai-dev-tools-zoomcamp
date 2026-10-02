from fastapi.testclient import TestClient


def test_health_reports_database_and_version(make_app):
    with TestClient(make_app(version="abc1234")) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "version": "abc1234"}


def test_health_is_503_when_the_database_is_down(make_app):
    app = make_app()
    with TestClient(app) as client:
        app.state.engine.dispose()
        down = app.state.engine.dialect.dbapi.OperationalError("db down")
        app.state.engine.pool._creator = lambda: (_ for _ in ()).throw(down)
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "error"
