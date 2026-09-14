from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


def create_settlement(
    client: TestClient, token: str, payer_id: str, recipient_id: str, amount: str = "50.00"
) -> dict:
    response = client.post(
        "/api/v1/settlements",
        json={"payer_id": payer_id, "recipient_id": recipient_id, "amount": amount},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateSettlement:
    def test_creates_pending_settlement(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        settlement = create_settlement(client, a_token, a["id"], b["id"], "50.00")
        assert settlement["status"] == "pending"
        assert settlement["amount"] == "50.00"

    def test_amount_must_be_positive(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        response = client.post(
            "/api/v1/settlements",
            json={"payer_id": a["id"], "recipient_id": b["id"], "amount": "0.00"},
            headers=auth_headers(a_token),
        )
        assert response.status_code == 400

    def test_payer_and_recipient_must_differ(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        a_token = login_as(client, "a", default_password("a"))
        response = client.post(
            "/api/v1/settlements",
            json={"payer_id": a["id"], "recipient_id": a["id"], "amount": "10.00"},
            headers=auth_headers(a_token),
        )
        assert response.status_code == 400


class TestConfirmRejectCancel:
    def test_recipient_confirms(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        b_token = login_as(client, "b", default_password("b"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/confirm", headers=auth_headers(b_token)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_payer_cannot_confirm_own_settlement(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/confirm", headers=auth_headers(a_token)
        )
        assert response.status_code == 403

    def test_recipient_rejects(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        b_token = login_as(client, "b", default_password("b"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/reject", headers=auth_headers(b_token)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"

    def test_payer_cancels(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/cancel", headers=auth_headers(a_token)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_recipient_cannot_cancel(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        b_token = login_as(client, "b", default_password("b"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/cancel", headers=auth_headers(b_token)
        )
        assert response.status_code == 403

    def test_cannot_confirm_already_resolved_settlement(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        b_token = login_as(client, "b", default_password("b"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        client.post(f"/api/v1/settlements/{settlement['id']}/reject", headers=auth_headers(b_token))
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/confirm", headers=auth_headers(b_token)
        )
        assert response.status_code == 400


class TestEditPendingSettlement:
    def test_payer_can_edit_pending_settlement(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        settlement = create_settlement(client, a_token, a["id"], b["id"], "50.00")
        response = client.patch(
            f"/api/v1/settlements/{settlement['id']}",
            json={"amount": "75.00"},
            headers=auth_headers(a_token),
        )
        assert response.status_code == 200
        assert response.json()["amount"] == "75.00"

    def test_cannot_edit_once_confirmed(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        b_token = login_as(client, "b", default_password("b"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        client.post(f"/api/v1/settlements/{settlement['id']}/confirm", headers=auth_headers(b_token))
        response = client.patch(
            f"/api/v1/settlements/{settlement['id']}",
            json={"amount": "75.00"},
            headers=auth_headers(a_token),
        )
        assert response.status_code == 400


class TestReversal:
    def _confirmed_settlement(self, client, admin_headers) -> tuple[dict, dict, str, str, dict]:
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        b_token = login_as(client, "b", default_password("b"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        client.post(f"/api/v1/settlements/{settlement['id']}/confirm", headers=auth_headers(b_token))
        return a, b, a_token, b_token, settlement

    def test_request_reversal_requires_confirmed_status(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        a_token = login_as(client, "a", default_password("a"))
        settlement = create_settlement(client, a_token, a["id"], b["id"])
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/request-reversal", headers=auth_headers(a_token)
        )
        assert response.status_code == 400

    def test_either_participant_can_request_reversal(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a, b, a_token, b_token, settlement = self._confirmed_settlement(client, admin_headers)
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/request-reversal", headers=auth_headers(a_token)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "reversal_pending"

    def test_other_participant_confirms_reversal(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a, b, a_token, b_token, settlement = self._confirmed_settlement(client, admin_headers)
        client.post(
            f"/api/v1/settlements/{settlement['id']}/request-reversal", headers=auth_headers(a_token)
        )
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/confirm-reversal", headers=auth_headers(b_token)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "reversed"

    def test_requester_cannot_confirm_their_own_reversal_request(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a, b, a_token, b_token, settlement = self._confirmed_settlement(client, admin_headers)
        client.post(
            f"/api/v1/settlements/{settlement['id']}/request-reversal", headers=auth_headers(a_token)
        )
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/confirm-reversal", headers=auth_headers(a_token)
        )
        assert response.status_code == 400

    def test_reject_reversal_returns_to_confirmed(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a, b, a_token, b_token, settlement = self._confirmed_settlement(client, admin_headers)
        client.post(
            f"/api/v1/settlements/{settlement['id']}/request-reversal", headers=auth_headers(a_token)
        )
        response = client.post(
            f"/api/v1/settlements/{settlement['id']}/reject-reversal", headers=auth_headers(b_token)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
