from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


def make_group(client: TestClient, admin_headers: dict[str, str], name: str, member_ids: list[str]) -> dict:
    return client.post(
        "/api/v1/groups", json={"name": name, "member_ids": member_ids}, headers=admin_headers
    ).json()


class TestCreateRefund:
    def test_creator_is_auto_confirmed(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Trip", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Returned tickets",
                "amount": "40.00",
                "participant_ids": [ana["id"], jaime["id"]],
            },
            headers=auth_headers(ana_token),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        confirmations = {c["user_id"]: c["confirmed"] for c in body["confirmations"]}
        assert confirmations == {ana["id"]: True, jaime["id"]: False}

    def test_participants_must_be_group_members(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        outsider = create_user(client, admin_headers, "outsider")
        group = make_group(client, admin_headers, "Trip", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        response = client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Oops",
                "amount": "10.00",
                "participant_ids": [ana["id"], outsider["id"]],
            },
            headers=auth_headers(ana_token),
        )
        assert response.status_code == 400

    def test_non_member_cannot_create_refund(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        create_user(client, admin_headers, "outsider")
        group = make_group(client, admin_headers, "Trip", [ana["id"]])
        outsider_token = login_as(client, "outsider", default_password("outsider"))
        response = client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Oops",
                "amount": "10.00",
                "participant_ids": [ana["id"]],
            },
            headers=auth_headers(outsider_token),
        )
        assert response.status_code == 403


class TestConfirmRefund:
    def test_pending_refund_does_not_affect_balances(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Trip", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Returned tickets",
                "amount": "40.00",
                "participant_ids": [ana["id"], jaime["id"]],
            },
            headers=auth_headers(ana_token),
        )
        balances = client.get(f"/api/v1/groups/{group['id']}/balances", headers=admin_headers).json()
        assert balances["pairs"] == []

    def test_balance_updates_only_after_every_participant_confirms(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Trip", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        refund = client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Returned tickets",
                "amount": "40.00",
                "participant_ids": [ana["id"], jaime["id"]],
            },
            headers=auth_headers(ana_token),
        ).json()

        response = client.post(
            f"/api/v1/refunds/{refund['id']}/confirm", headers=auth_headers(jaime_token)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

        balances = client.get(f"/api/v1/groups/{group['id']}/balances", headers=admin_headers).json()
        assert balances["pairs"] == [
            {"from_user_id": jaime["id"], "to_user_id": ana["id"], "amount": "20.00"}
        ]

    def test_non_participant_cannot_confirm(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        carlos = create_user(client, admin_headers, "carlos")
        group = make_group(client, admin_headers, "Trip", [ana["id"], jaime["id"], carlos["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        carlos_token = login_as(client, "carlos", default_password("carlos"))
        refund = client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Returned tickets",
                "amount": "40.00",
                "participant_ids": [ana["id"], jaime["id"]],
            },
            headers=auth_headers(ana_token),
        ).json()
        response = client.post(
            f"/api/v1/refunds/{refund['id']}/confirm", headers=auth_headers(carlos_token)
        )
        assert response.status_code == 400

    def test_already_confirmed_participant_cannot_reconfirm(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Trip", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        refund = client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Returned tickets",
                "amount": "40.00",
                "participant_ids": [ana["id"], jaime["id"]],
            },
            headers=auth_headers(ana_token),
        ).json()
        response = client.post(
            f"/api/v1/refunds/{refund['id']}/confirm", headers=auth_headers(ana_token)
        )
        assert response.status_code == 400


class TestListAndGetRefunds:
    def test_list_refunds(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Trip", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Returned tickets",
                "amount": "40.00",
                "participant_ids": [ana["id"]],
            },
            headers=auth_headers(ana_token),
        )
        response = client.get("/api/v1/refunds", headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_unknown_refund_404s(self, client: TestClient, admin_headers: dict[str, str]):
        response = client.get("/api/v1/refunds/does-not-exist", headers=admin_headers)
        assert response.status_code == 404
