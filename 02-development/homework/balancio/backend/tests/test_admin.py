from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


class TestAdminOverview:
    def test_returns_system_statistics(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = client.post(
            "/api/v1/groups",
            json={"name": "Home", "member_ids": [ana["id"], jaime["id"]]},
            headers=admin_headers,
        ).json()
        ana_token = login_as(client, "ana", default_password("ana"))
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Rent",
                "amount": "10.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": ana["id"], "amount": "10.00"}],
                "participant_ids": [ana["id"], jaime["id"]],
            },
            headers=auth_headers(ana_token),
        )
        client.post(
            "/api/v1/settlements",
            json={"payer_id": jaime["id"], "recipient_id": ana["id"], "amount": "5.00"},
            headers=auth_headers(jaime_token),
        )
        client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Refund",
                "amount": "2.00",
                "participant_ids": [ana["id"], jaime["id"]],
            },
            headers=auth_headers(ana_token),
        )

        response = client.get("/api/v1/admin/overview", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["users_count"] == 3
        assert body["active_users_count"] == 3
        assert body["groups_count"] == 1
        assert body["active_groups_count"] == 1
        assert body["expenses_count"] == 1
        assert body["pending_settlements_count"] == 1
        assert body["pending_refunds_count"] == 1

    def test_non_admin_forbidden(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "ana")
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.get("/api/v1/admin/overview", headers=auth_headers(ana_token))
        assert response.status_code == 403

    def test_requires_authentication(self, client: TestClient):
        response = client.get("/api/v1/admin/overview")
        assert response.status_code == 401
