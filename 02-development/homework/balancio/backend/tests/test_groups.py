from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


def make_group(client: TestClient, admin_headers: dict[str, str], name: str, member_ids: list[str]) -> dict:
    response = client.post(
        "/api/v1/groups", json={"name": name, "member_ids": member_ids}, headers=admin_headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_expense(
    client: TestClient,
    token: str,
    group_id: str,
    payer_id: str,
    amount: str,
    participant_ids: list[str],
) -> dict:
    response = client.post(
        "/api/v1/expenses",
        json={
            "group_id": group_id,
            "title": "Expense",
            "amount": amount,
            "expense_date": "2026-01-01",
            "payers": [{"user_id": payer_id, "amount": amount}],
            "participant_ids": participant_ids,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateGroup:
    def test_admin_can_create_group(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        assert group["status"] == "active"
        assert group["member_ids"] == [ana["id"]]

    def test_non_admin_cannot_create_group(self, client: TestClient, admin_headers: dict[str, str]):
        create_user(client, admin_headers, "ana")
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.post(
            "/api/v1/groups", json={"name": "Home", "member_ids": []}, headers=auth_headers(ana_token)
        )
        assert response.status_code == 403

    def test_name_is_required(self, client: TestClient, admin_headers: dict[str, str]):
        response = client.post(
            "/api/v1/groups", json={"name": "  ", "member_ids": []}, headers=admin_headers
        )
        assert response.status_code == 400


class TestListAndVisibility:
    def test_admin_sees_all_groups(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        make_group(client, admin_headers, "Home", [ana["id"]])
        make_group(client, admin_headers, "Trip", [])
        response = client.get("/api/v1/groups", headers=admin_headers)
        assert len(response.json()) == 2

    def test_regular_user_sees_only_their_groups(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        make_group(client, admin_headers, "Home", [ana["id"]])
        make_group(client, admin_headers, "Trip", [jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.get("/api/v1/groups", headers=auth_headers(ana_token))
        names = [g["name"] for g in response.json()]
        assert names == ["Home"]

    def test_non_member_cannot_view_group_detail(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        response = client.get(f"/api/v1/groups/{group['id']}", headers=auth_headers(jaime_token))
        assert response.status_code == 403


class TestMembership:
    def test_admin_adds_member(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        response = client.post(
            f"/api/v1/groups/{group['id']}/members",
            json={"user_id": jaime["id"]},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert set(response.json()["member_ids"]) == {ana["id"], jaime["id"]}

    def test_cannot_add_member_to_archived_group(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        client.post(f"/api/v1/groups/{group['id']}/archive", headers=admin_headers)
        response = client.post(
            f"/api/v1/groups/{group['id']}/members",
            json={"user_id": jaime["id"]},
            headers=admin_headers,
        )
        assert response.status_code == 400

    def test_remove_member_blocked_when_balance_nonzero(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        add_expense(client, jaime_token, group["id"], jaime["id"], "100.00", [jaime["id"], ana["id"]])
        response = client.delete(
            f"/api/v1/groups/{group['id']}/members/{ana['id']}", headers=admin_headers
        )
        assert response.status_code == 400

    def test_remove_member_allowed_when_balance_zero(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        response = client.delete(
            f"/api/v1/groups/{group['id']}/members/{ana['id']}", headers=admin_headers
        )
        assert response.status_code == 200
        assert ana["id"] not in response.json()["member_ids"]


class TestLeaveGroup:
    def test_cannot_leave_with_nonzero_balance(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        add_expense(client, jaime_token, group["id"], jaime["id"], "100.00", [jaime["id"], ana["id"]])
        response = client.post(f"/api/v1/groups/{group['id']}/leave", headers=auth_headers(jaime_token))
        assert response.status_code == 400

    def test_can_leave_with_zero_balance(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        response = client.post(f"/api/v1/groups/{group['id']}/leave", headers=auth_headers(jaime_token))
        assert response.status_code == 200
        assert jaime["id"] not in response.json()["member_ids"]


class TestArchive:
    def test_cannot_archive_with_nonzero_balances(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        add_expense(client, jaime_token, group["id"], jaime["id"], "100.00", [jaime["id"], ana["id"]])
        response = client.post(f"/api/v1/groups/{group['id']}/archive", headers=admin_headers)
        assert response.status_code == 400

    def test_can_archive_when_settled(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        response = client.post(f"/api/v1/groups/{group['id']}/archive", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "archived"

    def test_non_admin_cannot_archive(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.post(f"/api/v1/groups/{group['id']}/archive", headers=auth_headers(ana_token))
        assert response.status_code == 403


class TestGroupBalances:
    def test_returns_pairwise_breakdown(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        add_expense(client, ana_token, group["id"], ana["id"], "600.00", [ana["id"], jaime["id"]])
        response = client.get(f"/api/v1/groups/{group['id']}/balances", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["pairs"] == [
            {"from_user_id": jaime["id"], "to_user_id": ana["id"], "amount": "300.00"}
        ]

    def test_forbidden_for_non_member(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        response = client.get(
            f"/api/v1/groups/{group['id']}/balances", headers=auth_headers(jaime_token)
        )
        assert response.status_code == 403
