from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


def make_group(client: TestClient, admin_headers: dict[str, str], name: str, member_ids: list[str]) -> dict:
    return client.post(
        "/api/v1/groups", json={"name": name, "member_ids": member_ids}, headers=admin_headers
    ).json()


def make_expense(client, token, group_id, payer_id, participant_ids) -> dict:
    return client.post(
        "/api/v1/expenses",
        json={
            "group_id": group_id,
            "title": "Groceries",
            "amount": "20.00",
            "expense_date": "2026-01-01",
            "payers": [{"user_id": payer_id, "amount": "20.00"}],
            "participant_ids": participant_ids,
        },
        headers=auth_headers(token),
    ).json()


class TestCreateComment:
    def test_involved_user_can_comment(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"], jaime["id"]])

        response = client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Thanks!"},
            headers=auth_headers(jaime_token),
        )
        assert response.status_code == 201
        assert response.json()["body"] == "Thanks!"
        assert response.json()["author_id"] == jaime["id"]

    def test_uninvolved_user_cannot_comment(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        carlos = create_user(client, admin_headers, "carlos")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"], carlos["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        carlos_token = login_as(client, "carlos", default_password("carlos"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"], jaime["id"]])

        response = client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Sneaky"},
            headers=auth_headers(carlos_token),
        )
        assert response.status_code == 403

    def test_empty_body_rejected(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"]])
        response = client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": ""},
            headers=auth_headers(ana_token),
        )
        assert response.status_code == 422

    def test_comment_on_settlement_by_participant(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        settlement = client.post(
            "/api/v1/settlements",
            json={"payer_id": a["id"], "recipient_id": b["id"], "amount": "10.00"},
            headers=auth_headers(a_token),
        ).json()
        response = client.post(
            f"/api/v1/settlement/{settlement['id']}/comments",
            json={"body": "Sent!"},
            headers=auth_headers(a_token),
        )
        assert response.status_code == 201

    def test_comment_on_refund_by_non_participant_forbidden(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        ana = create_user(client, admin_headers, "ana")
        carlos = create_user(client, admin_headers, "carlos")
        group = make_group(client, admin_headers, "Trip", [ana["id"], carlos["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        carlos_token = login_as(client, "carlos", default_password("carlos"))
        refund = client.post(
            "/api/v1/refunds",
            json={
                "group_id": group["id"],
                "title": "Refund",
                "amount": "10.00",
                "participant_ids": [ana["id"]],
            },
            headers=auth_headers(ana_token),
        ).json()
        response = client.post(
            f"/api/v1/refund/{refund['id']}/comments",
            json={"body": "Hey"},
            headers=auth_headers(carlos_token),
        )
        assert response.status_code == 403


class TestListComments:
    def test_list_comments_oldest_first(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"]])
        client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "First"},
            headers=auth_headers(ana_token),
        )
        client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Second"},
            headers=auth_headers(ana_token),
        )
        response = client.get(f"/api/v1/expense/{expense['id']}/comments", headers=auth_headers(ana_token))
        assert [c["body"] for c in response.json()] == ["First", "Second"]


class TestEditDeleteComment:
    def test_author_can_edit(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"]])
        comment = client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Original"},
            headers=auth_headers(ana_token),
        ).json()
        response = client.patch(
            f"/api/v1/comments/{comment['id']}", json={"body": "Edited"}, headers=auth_headers(ana_token)
        )
        assert response.status_code == 200
        assert response.json()["body"] == "Edited"

    def test_non_author_cannot_edit(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        jaime = create_user(client, admin_headers, "jaime")
        group = make_group(client, admin_headers, "Home", [ana["id"], jaime["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"], jaime["id"]])
        comment = client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Original"},
            headers=auth_headers(ana_token),
        ).json()
        response = client.patch(
            f"/api/v1/comments/{comment['id']}", json={"body": "Hijacked"}, headers=auth_headers(jaime_token)
        )
        assert response.status_code == 403

    def test_admin_cannot_edit_others_comment(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"]])
        comment = client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Original"},
            headers=auth_headers(ana_token),
        ).json()
        response = client.patch(
            f"/api/v1/comments/{comment['id']}", json={"body": "Admin edit"}, headers=admin_headers
        )
        assert response.status_code == 403

    def test_author_can_delete(self, client: TestClient, admin_headers: dict[str, str]):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"]])
        comment = client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Original"},
            headers=auth_headers(ana_token),
        ).json()
        response = client.delete(f"/api/v1/comments/{comment['id']}", headers=auth_headers(ana_token))
        assert response.status_code == 204
        remaining = client.get(f"/api/v1/expense/{expense['id']}/comments", headers=auth_headers(ana_token))
        assert remaining.json() == []

    def test_deleting_expense_cascades_its_comments(
        self, client: TestClient, admin_headers: dict[str, str], app
    ):
        ana = create_user(client, admin_headers, "ana")
        group = make_group(client, admin_headers, "Home", [ana["id"]])
        ana_token = login_as(client, "ana", default_password("ana"))
        expense = make_expense(client, ana_token, group["id"], ana["id"], [ana["id"]])
        client.post(
            f"/api/v1/expense/{expense['id']}/comments",
            json={"body": "Bye"},
            headers=auth_headers(ana_token),
        )
        client.delete(f"/api/v1/expenses/{expense['id']}", headers=auth_headers(ana_token))
        assert app.state.store.read("comments") == []
