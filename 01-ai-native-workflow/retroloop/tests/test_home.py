import pytest


@pytest.mark.django_db
def test_homepage_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
