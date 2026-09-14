from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


class TestCreateUser:
    def test_admin_can_create_user(self, client: TestClient, admin_headers: dict[str, str]):
        user = create_user(client, admin_headers, "sam")
        assert user["role"] == "user"
        assert user["must_change_password"] is True
        assert user["is_active"] is True

    def test_non_admin_cannot_create_user(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "sam")
        sam_token = login_as(client, "sam", default_password("sam"))
        response = client.post(
            "/api/v1/users",
            json={"username": "eve", "display_name": "Eve", "temporary_password": "eve123456"},
            headers=auth_headers(sam_token),
        )
        assert response.status_code == 403

    def test_duplicate_username_rejected(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "sam")
        response = client.post(
            "/api/v1/users",
            json={"username": "sam", "display_name": "Sam 2", "temporary_password": default_password("sam")},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_requires_authentication(self, client: TestClient):
        response = client.post(
            "/api/v1/users",
            json={"username": "sam", "display_name": "Sam", "temporary_password": default_password("sam")},
        )
        assert response.status_code == 401


class TestListAndGetUsers:
    def test_list_users(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "sam")
        response = client.get("/api/v1/users", headers=admin_headers)
        assert response.status_code == 200
        usernames = {u["username"] for u in response.json()}
        assert {"admin", "sam"} <= usernames

    def test_get_unknown_user_404s(self, client: TestClient, admin_headers: dict[str, str]):
        response = client.get("/api/v1/users/does-not-exist", headers=admin_headers)
        assert response.status_code == 404


class TestUpdateUser:
    def test_self_update_display_name(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        sam_token = login_as(client, "sam", default_password("sam"))
        response = client.patch(
            f"/api/v1/users/{sam['id']}",
            json={"display_name": "Sammy"},
            headers=auth_headers(sam_token),
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Sammy"

    def test_cannot_update_other_users_profile(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        create_user(client, admin_headers, "eve")
        eve_token = login_as(client, "eve", default_password("eve"))
        response = client.patch(
            f"/api/v1/users/{sam['id']}",
            json={"display_name": "Hacked"},
            headers=auth_headers(eve_token),
        )
        assert response.status_code == 403

    def test_admin_can_update_any_profile(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        response = client.patch(
            f"/api/v1/users/{sam['id']}",
            json={"display_name": "Renamed"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Renamed"

    def test_can_update_own_theme(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        sam_token = login_as(client, "sam", default_password("sam"))
        response = client.patch(
            f"/api/v1/users/{sam['id']}", json={"theme": "dark"}, headers=auth_headers(sam_token)
        )
        assert response.status_code == 200
        assert response.json()["theme"] == "dark"


class TestPasswordAdminActions:
    def test_reset_password_forces_change_and_updates_credentials(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        sam = create_user(client, admin_headers, "sam")
        response = client.post(
            f"/api/v1/users/{sam['id']}/reset-password",
            json={"new_temporary_password": "brandnew123"},
            headers=admin_headers,
        )
        assert response.status_code == 204
        # old password no longer works
        assert client.post(
            "/api/v1/auth/login", json={"username": "sam", "password": default_password("sam")}
        ).status_code == 401
        token = login_as(client, "sam", "brandnew123")
        me = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()
        assert me["must_change_password"] is True

    def test_non_admin_cannot_reset_password(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        create_user(client, admin_headers, "eve")
        eve_token = login_as(client, "eve", default_password("eve"))
        response = client.post(
            f"/api/v1/users/{sam['id']}/reset-password",
            json={"new_temporary_password": "brandnew123"},
            headers=auth_headers(eve_token),
        )
        assert response.status_code == 403

    def test_force_password_change(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        sam_token = login_as(client, "sam", default_password("sam"))
        client.post(
            "/api/v1/auth/change-password",
            json={"old_password": default_password("sam"), "new_password": "newpassword1"},
            headers=auth_headers(sam_token),
        )
        response = client.post(
            f"/api/v1/users/{sam['id']}/force-password-change", headers=admin_headers
        )
        assert response.status_code == 204
        token = login_as(client, "sam", "newpassword1")
        me = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()
        assert me["must_change_password"] is True


class TestActivateDeactivate:
    def test_deactivate_user_with_zero_balance(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        response = client.post(f"/api/v1/users/{sam['id']}/deactivate", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_deactivate_blocked_when_balance_nonzero(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = client.post(
            "/api/v1/groups",
            json={"name": "Home", "member_ids": [ana["id"], jaime["id"]]},
            headers=admin_headers,
        ).json()
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Rent",
                "amount": "100.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": jaime["id"], "amount": "100.00"}],
                "participant_ids": [jaime["id"], ana["id"]],
            },
            headers=auth_headers(jaime_token),
        )
        response = client.post(f"/api/v1/users/{ana['id']}/deactivate", headers=admin_headers)
        assert response.status_code == 400
        assert "balance" in response.json()["message"]

    def test_activate_reactivates_user(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        client.post(f"/api/v1/users/{sam['id']}/deactivate", headers=admin_headers)
        response = client.post(f"/api/v1/users/{sam['id']}/activate", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["is_active"] is True
        # can log in again
        assert client.post(
            "/api/v1/auth/login", json={"username": "sam", "password": default_password("sam")}
        ).status_code == 200

    def test_non_admin_cannot_deactivate(self, client: TestClient, admin_headers: dict[str, str]):
        sam = create_user(client, admin_headers, "sam")
        create_user(client, admin_headers, "eve")
        eve_token = login_as(client, "eve", default_password("eve"))
        response = client.post(
            f"/api/v1/users/{sam['id']}/deactivate", headers=auth_headers(eve_token)
        )
        assert response.status_code == 403
