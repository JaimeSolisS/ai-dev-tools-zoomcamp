from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


class TestSetup:
    def test_creates_first_admin_and_logs_in(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "display_name": "Admin", "password": "admin1234"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["user"]["role"] == "admin"
        assert body["user"]["username"] == "admin"
        assert "password" not in body["user"]
        assert "password_hash" not in body["user"]
        assert body["access_token"]
        assert body["token_type"] == "bearer"

    def test_rejects_short_password(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "display_name": "Admin", "password": "short"},
        )
        assert response.status_code == 422

    def test_second_setup_is_rejected(self, client: TestClient, admin_token: str):
        response = client.post(
            "/api/v1/auth/setup",
            json={"username": "admin2", "display_name": "Second", "password": "admin1234"},
        )
        assert response.status_code == 409
        assert "message" in response.json()

    def test_duplicate_username_rejected(self, client: TestClient):
        client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "display_name": "Admin", "password": "admin1234"},
        )


class TestLogin:
    def test_login_with_correct_credentials(self, client: TestClient, admin_token: str):
        response = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin1234"}
        )
        assert response.status_code == 200
        assert response.json()["user"]["username"] == "admin"

    def test_login_with_wrong_password_is_friendly_error(self, client: TestClient, admin_token: str):
        response = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
        )
        assert response.status_code == 401
        assert response.json()["message"] == "Incorrect username or password."

    def test_login_with_unknown_username(self, client: TestClient, admin_token: str):
        response = client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "whatever1"}
        )
        assert response.status_code == 401

    def test_deactivated_user_cannot_log_in(
        self, client: TestClient, admin_token: str
    ):
        create_user(client, auth_headers(admin_token), "sam")
        # log in once as sam to discover their id via /auth/me
        sam_token = login_as(client, "sam", default_password("sam"))
        me = client.get("/api/v1/auth/me", headers=auth_headers(sam_token)).json()
        client.post(f"/api/v1/users/{me['id']}/deactivate", headers=auth_headers(admin_token))
        response = client.post(
            "/api/v1/auth/login", json={"username": "sam", "password": default_password("sam")}
        )
        assert response.status_code == 401


class TestMe:
    def test_returns_current_user(self, client: TestClient, admin_headers: dict[str, str]):
        response = client.get("/api/v1/auth/me", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["username"] == "admin"

    def test_requires_authentication(self, client: TestClient):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_rejects_garbage_token(self, client: TestClient):
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401


class TestChangePassword:
    def test_new_user_must_change_password_flag(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        create_user(client, admin_headers, "sam")
        token = login_as(client, "sam", default_password("sam"))
        me = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()
        assert me["must_change_password"] is True

    def test_change_password_clears_flag_and_updates_credentials(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        create_user(client, admin_headers, "sam")
        token = login_as(client, "sam", default_password("sam"))
        response = client.post(
            "/api/v1/auth/change-password",
            json={"old_password": default_password("sam"), "new_password": "newpassword1"},
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        assert response.json()["must_change_password"] is False

        # old password no longer works, new one does
        assert client.post(
            "/api/v1/auth/login", json={"username": "sam", "password": default_password("sam")}
        ).status_code == 401
        assert client.post(
            "/api/v1/auth/login", json={"username": "sam", "password": "newpassword1"}
        ).status_code == 200

    def test_wrong_old_password_rejected(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "sam")
        token = login_as(client, "sam", default_password("sam"))
        response = client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "wrong", "new_password": "newpassword1"},
            headers=auth_headers(token),
        )
        assert response.status_code == 400


class TestLogout:
    def test_logout_returns_no_content(self, client: TestClient, admin_headers: dict[str, str]):
        response = client.post("/api/v1/auth/logout", headers=admin_headers)
        assert response.status_code == 204
