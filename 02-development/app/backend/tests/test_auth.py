from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .conftest import PASSWORD, assert_error, bearer, sign_up


def test_login_returns_user_and_bearer_token(client, store):
    store.create_user("ada@example.com", "Ada Lovelace", password=PASSWORD)
    response = client.post("/v1/auth/login", json={"email": " ADA@example.com ", "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["displayName"] == "Ada Lovelace"
    assert set(body["user"]) == {"id", "email", "displayName", "organizationId", "createdAt"}
    me = client.get("/v1/auth/me", headers=bearer(body["accessToken"]))
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]


def test_login_rejects_bad_credentials_with_the_same_error(client, store):
    store.create_user("ada@example.com", password=PASSWORD)
    store.create_user("magic@example.com")  # no password: magic-link only
    for email, password in [("ada@example.com", "nope"), ("nobody@example.com", PASSWORD), ("magic@example.com", "")]:
        response = client.post("/v1/auth/login", json={"email": email, "password": password})
        assert_error(response, 401, "UNAUTHENTICATED")
        assert response.json()["message"] == "Invalid email or password."


def test_passwords_and_tokens_are_not_stored_in_plain_text(client, store):
    headers = sign_up(client, store)
    token = headers["Authorization"].removeprefix("Bearer ")
    user = store.find_user_by_email("ada@example.com")
    assert user.password_hash and PASSWORD not in user.password_hash
    assert token not in store.access_tokens
    assert "passwordHash" not in client.get("/v1/auth/me", headers=headers).text


def test_me_requires_a_valid_bearer_token(client):
    assert_error(client.get("/v1/auth/me"), 401, "UNAUTHENTICATED")
    assert_error(client.get("/v1/auth/me", headers=bearer("forged")), 401, "UNAUTHENTICATED")
    assert_error(client.get("/v1/auth/me", headers={"Authorization": "Basic abc"}), 401, "UNAUTHENTICATED")
    assert client.get("/v1/auth/me").headers["www-authenticate"] == "Bearer"


def test_logout_revokes_the_token(client, store):
    headers = sign_up(client, store)
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    assert_error(client.get("/v1/auth/me", headers=headers), 401, "UNAUTHENTICATED")
    # Idempotent, and fine without a token.
    assert client.post("/v1/auth/logout", headers=headers).status_code == 204
    assert client.post("/v1/auth/logout").status_code == 204


def test_magic_link_flow_creates_user_with_example_session(client, store):
    from app.seed import create_example_session

    store.on_user_created = create_example_session
    response = client.post("/v1/auth/magic-link", json={"email": "Grace@Example.com"})
    assert response.status_code == 200
    token = response.json()["devToken"]
    verified = client.post("/v1/auth/magic-link/verify", json={"token": token})
    assert verified.status_code == 200
    body = verified.json()
    assert body["user"]["email"] == "grace@example.com"
    assert body["user"]["displayName"] == "Grace"
    sessions = client.get("/v1/sessions", headers=bearer(body["accessToken"])).json()
    assert [s["title"] for s in sessions] == ["Example: Design a URL shortener"]


def test_magic_link_is_single_use_and_expires(client, clock):
    token = client.post("/v1/auth/magic-link", json={"email": "a@b.co"}).json()["devToken"]
    assert client.post("/v1/auth/magic-link/verify", json={"token": token}).status_code == 200
    assert_error(client.post("/v1/auth/magic-link/verify", json={"token": token}), 404, "LINK_INVALID")

    token = client.post("/v1/auth/magic-link", json={"email": "a@b.co"}).json()["devToken"]
    clock.advance(minutes=16)
    assert_error(client.post("/v1/auth/magic-link/verify", json={"token": token}), 404, "LINK_INVALID")


def test_magic_link_for_existing_user_signs_them_in(client, store):
    store.create_user("ada@example.com", password=PASSWORD)
    token = client.post("/v1/auth/magic-link", json={"email": "ada@example.com"}).json()["devToken"]
    body = client.post("/v1/auth/magic-link/verify", json={"token": token}).json()
    assert body["user"]["id"] == store.find_user_by_email("ada@example.com").id
    assert len(store.users) == 1


def test_magic_link_validates_email(client):
    response = client.post("/v1/auth/magic-link", json={"email": "not-an-email"})
    assert_error(response, 422, "VALIDATION")
    assert response.json()["message"] == "Enter a valid email address."
    assert_error(client.post("/v1/auth/magic-link", json={}), 422, "VALIDATION")


def test_dev_token_is_not_returned_outside_dev_mode():
    with TestClient(create_app(Settings(seed=False, dev_mode=False))) as client:
        response = client.post("/v1/auth/magic-link", json={"email": "a@b.co"})
        assert response.json() == {"sent": True}
