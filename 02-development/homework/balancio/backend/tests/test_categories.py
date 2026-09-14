from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


class TestCreateCategory:
    def test_admin_creates_global_category(self, client: TestClient, admin_headers: dict[str, str]):
        response = client.post("/api/v1/categories", json={"name": "Groceries"}, headers=admin_headers)
        assert response.status_code == 201
        assert response.json()["group_id"] is None

    def test_admin_creates_group_specific_category(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        group = client.post(
            "/api/v1/groups", json={"name": "Trip", "member_ids": []}, headers=admin_headers
        ).json()
        response = client.post(
            "/api/v1/categories",
            json={"name": "Souvenirs", "group_id": group["id"]},
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["group_id"] == group["id"]

    def test_non_admin_cannot_create_category(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "ana")
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.post(
            "/api/v1/categories", json={"name": "Groceries"}, headers=auth_headers(ana_token)
        )
        assert response.status_code == 403


class TestListCategories:
    def test_list_includes_global_and_group_specific(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        group = client.post(
            "/api/v1/groups", json={"name": "Trip", "member_ids": []}, headers=admin_headers
        ).json()
        client.post("/api/v1/categories", json={"name": "Groceries"}, headers=admin_headers)
        client.post(
            "/api/v1/categories",
            json={"name": "Souvenirs", "group_id": group["id"]},
            headers=admin_headers,
        )
        response = client.get(
            "/api/v1/categories", params={"group_id": group["id"]}, headers=admin_headers
        )
        names = {c["name"] for c in response.json()}
        assert names == {"Groceries", "Souvenirs"}

    def test_group_specific_category_not_visible_to_other_groups(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        group_a = client.post(
            "/api/v1/groups", json={"name": "A", "member_ids": []}, headers=admin_headers
        ).json()
        group_b = client.post(
            "/api/v1/groups", json={"name": "B", "member_ids": []}, headers=admin_headers
        ).json()
        client.post(
            "/api/v1/categories",
            json={"name": "Souvenirs", "group_id": group_a["id"]},
            headers=admin_headers,
        )
        response = client.get(
            "/api/v1/categories", params={"group_id": group_b["id"]}, headers=admin_headers
        )
        assert response.json() == []


class TestUpdateDeleteCategory:
    def test_admin_renames_category(self, client: TestClient, admin_headers: dict[str, str]):
        category = client.post(
            "/api/v1/categories", json={"name": "Food"}, headers=admin_headers
        ).json()
        response = client.patch(
            f"/api/v1/categories/{category['id']}", json={"name": "Dining"}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Dining"

    def test_delete_unused_category(self, client: TestClient, admin_headers: dict[str, str]):
        category = client.post(
            "/api/v1/categories", json={"name": "Food"}, headers=admin_headers
        ).json()
        response = client.delete(f"/api/v1/categories/{category['id']}", headers=admin_headers)
        assert response.status_code == 204

    def test_delete_blocked_when_used_by_expense(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        group = client.post(
            "/api/v1/groups", json={"name": "Home", "member_ids": [ana["id"]]}, headers=admin_headers
        ).json()
        category = client.post(
            "/api/v1/categories", json={"name": "Food"}, headers=admin_headers
        ).json()
        ana_token = login_as(client, "ana", default_password("ana"))
        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Groceries",
                "amount": "10.00",
                "expense_date": "2026-01-01",
                "category_id": category["id"],
                "payers": [{"user_id": ana["id"], "amount": "10.00"}],
                "participant_ids": [ana["id"]],
            },
            headers=auth_headers(ana_token),
        )
        response = client.delete(f"/api/v1/categories/{category['id']}", headers=admin_headers)
        assert response.status_code == 400

    def test_non_admin_cannot_delete(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "ana")
        ana_token = login_as(client, "ana", default_password("ana"))
        category = client.post(
            "/api/v1/categories", json={"name": "Food"}, headers=admin_headers
        ).json()
        response = client.delete(
            f"/api/v1/categories/{category['id']}", headers=auth_headers(ana_token)
        )
        assert response.status_code == 403
