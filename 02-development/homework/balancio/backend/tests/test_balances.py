from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


def make_group(client: TestClient, admin_headers: dict[str, str], name: str, member_ids: list[str]) -> dict:
    return client.post(
        "/api/v1/groups", json={"name": name, "member_ids": member_ids}, headers=admin_headers
    ).json()


def add_expense(client, token, group_id, payer_id, amount, participant_ids) -> dict:
    return client.post(
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
    ).json()


class TestGlobalBalances:
    def test_nets_across_groups_matching_spec_example(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        home = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        trip = make_group(client, admin_headers, "Trip", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        add_expense(client, ana_token, home["id"], ana["id"], "600.00", [ana["id"], jaime["id"]])
        add_expense(client, jaime_token, trip["id"], jaime["id"], "300.00", [jaime["id"], ana["id"]])

        response = client.get("/api/v1/balances/global", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["confirmed"]["pairs"] == [
            {"from_user_id": jaime["id"], "to_user_id": ana["id"], "amount": "150.00"}
        ]
        assert body["current"]["pairs"] == body["confirmed"]["pairs"]

    def test_pending_settlement_only_changes_current_balance(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        add_expense(client, ana_token, group["id"], ana["id"], "100.00", [ana["id"], jaime["id"]])
        client.post(
            "/api/v1/settlements",
            json={"payer_id": jaime["id"], "recipient_id": ana["id"], "amount": "50.00"},
            headers=auth_headers(jaime_token),
        )

        body = client.get("/api/v1/balances/global", headers=admin_headers).json()
        assert body["confirmed"]["pairs"] == [
            {"from_user_id": jaime["id"], "to_user_id": ana["id"], "amount": "50.00"}
        ]
        assert body["current"]["pairs"] == []

    def test_balances_me_is_accessible_to_any_authenticated_user(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        create_user(client, admin_headers, "ana")
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.get("/api/v1/balances/me", headers=auth_headers(ana_token))
        assert response.status_code == 200

    def test_requires_authentication(self, client: TestClient):
        assert client.get("/api/v1/balances/global").status_code == 401


class TestSettlementSuggestions:
    def test_simplifies_a_debt_chain(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        carlos = create_user(client, admin_headers, "carlos")
        group = make_group(
            client, admin_headers, "Poker", [ana["id"], jaime["id"], carlos["id"]]
        )
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        carlos_token = login_as(client, "carlos", default_password("carlos"))
        # Ana owes Jaime $20; Jaime owes Carlos $20 -> should simplify to
        # Ana -> Carlos $20.
        add_expense(client, jaime_token, group["id"], jaime["id"], "40.00", [jaime["id"], ana["id"]])
        add_expense(client, carlos_token, group["id"], carlos["id"], "40.00", [carlos["id"], jaime["id"]])

        response = client.get("/api/v1/settlement-suggestions", headers=admin_headers)
        assert response.status_code == 200
        pairs = response.json()
        assert pairs == [{"from_user_id": ana["id"], "to_user_id": carlos["id"], "amount": "20.00"}]
