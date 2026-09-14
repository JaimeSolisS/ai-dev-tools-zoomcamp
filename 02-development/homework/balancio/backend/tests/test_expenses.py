from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_user, default_password, login_as


def make_group(client: TestClient, admin_headers: dict[str, str], name: str, member_ids: list[str]) -> dict:
    response = client.post(
        "/api/v1/groups", json={"name": name, "member_ids": member_ids}, headers=admin_headers
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateExpense:
    def test_equal_split_with_remainder_cents(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        c = create_user(client, admin_headers, "c")
        group = make_group(client, admin_headers, "Trio", [a["id"], b["id"], c["id"]])
        a_token = login_as(client, "a", default_password("a"))
        response = client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Dinner",
                "amount": "100.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "100.00"}],
                "participant_ids": [a["id"], b["id"], c["id"]],
            },
            headers=auth_headers(a_token),
        )
        assert response.status_code == 201, response.text
        shares = {s["user_id"]: s["amount"] for s in response.json()["shares"]}
        assert sum(float(v) for v in shares.values()) == 100.00
        assert sorted(shares.values()) == ["33.33", "33.33", "33.34"]

    def test_multiple_payers(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        group = make_group(client, admin_headers, "Pair", [a["id"], b["id"]])
        a_token = login_as(client, "a", default_password("a"))
        response = client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Groceries",
                "amount": "100.00",
                "expense_date": "2026-01-01",
                "payers": [
                    {"user_id": a["id"], "amount": "60.00"},
                    {"user_id": b["id"], "amount": "40.00"},
                ],
                "participant_ids": [a["id"], b["id"]],
            },
            headers=auth_headers(a_token),
        )
        assert response.status_code == 201

    def test_payer_amounts_must_sum_to_total(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        group = make_group(client, admin_headers, "Pair", [a["id"], b["id"]])
        a_token = login_as(client, "a", default_password("a"))
        response = client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Bad split",
                "amount": "100.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "50.00"}],
                "participant_ids": [a["id"], b["id"]],
            },
            headers=auth_headers(a_token),
        )
        assert response.status_code == 400
        assert "Payer amounts" in response.json()["message"]

    def test_payer_need_not_be_a_participant(self, client: TestClient, admin_headers: dict[str, str]):
        jaime = create_user(client, admin_headers, "jaime")
        ana = create_user(client, admin_headers, "ana")
        carlos = create_user(client, admin_headers, "carlos")
        group = make_group(client, admin_headers, "Trip", [jaime["id"], ana["id"], carlos["id"]])
        jaime_token = login_as(client, "jaime", default_password("jaime"))
        response = client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Hotel",
                "amount": "300.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": jaime["id"], "amount": "300.00"}],
                "participant_ids": [ana["id"], carlos["id"]],
            },
            headers=auth_headers(jaime_token),
        )
        assert response.status_code == 201
        shares = {s["user_id"] for s in response.json()["shares"]}
        assert shares == {ana["id"], carlos["id"]}

    def test_participants_must_be_group_members(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        outsider = create_user(client, admin_headers, "outsider")
        group = make_group(client, admin_headers, "Solo", [a["id"]])
        a_token = login_as(client, "a", default_password("a"))
        response = client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Oops",
                "amount": "10.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "10.00"}],
                "participant_ids": [a["id"], outsider["id"]],
            },
            headers=auth_headers(a_token),
        )
        assert response.status_code == 400

    def test_non_member_cannot_create_expense(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        create_user(client, admin_headers, "outsider")
        group = make_group(client, admin_headers, "Solo", [a["id"]])
        outsider_token = login_as(client, "outsider", default_password("outsider"))
        response = client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Oops",
                "amount": "10.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "10.00"}],
                "participant_ids": [a["id"]],
            },
            headers=auth_headers(outsider_token),
        )
        assert response.status_code == 403

    def test_cannot_add_expense_to_archived_group(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        group = make_group(client, admin_headers, "Solo", [a["id"]])
        client.post(f"/api/v1/groups/{group['id']}/archive", headers=admin_headers)
        a_token = login_as(client, "a", default_password("a"))
        response = client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Oops",
                "amount": "10.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "10.00"}],
                "participant_ids": [a["id"]],
            },
            headers=auth_headers(a_token),
        )
        assert response.status_code == 400


class TestEditAndDeleteExpense:
    def _create(self, client: TestClient, admin_headers: dict[str, str]) -> tuple[dict, dict, dict, str]:
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        group = make_group(client, admin_headers, "Pair", [a["id"], b["id"]])
        a_token = login_as(client, "a", default_password("a"))
        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Groceries",
                "amount": "50.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "50.00"}],
                "participant_ids": [a["id"], b["id"]],
            },
            headers=auth_headers(a_token),
        ).json()
        return a, b, group, a_token

    def test_creator_can_edit(self, client: TestClient, admin_headers: dict[str, str]):
        a, b, group, a_token = self._create(client, admin_headers)
        expense = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"][0]
        response = client.patch(
            f"/api/v1/expenses/{expense['id']}", json={"title": "Renamed"}, headers=auth_headers(a_token)
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Renamed"

    def test_other_member_cannot_edit(self, client: TestClient, admin_headers: dict[str, str]):
        a, b, group, a_token = self._create(client, admin_headers)
        b_token = login_as(client, "b", default_password("b"))
        expense = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"][0]
        response = client.patch(
            f"/api/v1/expenses/{expense['id']}", json={"title": "Hijacked"}, headers=auth_headers(b_token)
        )
        assert response.status_code == 403

    def test_admin_can_edit_any_expense(self, client: TestClient, admin_headers: dict[str, str]):
        a, b, group, a_token = self._create(client, admin_headers)
        expense = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"][0]
        response = client.patch(
            f"/api/v1/expenses/{expense['id']}", json={"title": "Admin edit"}, headers=admin_headers
        )
        assert response.status_code == 200

    def test_edit_blocked_when_confirmed_settlement_exists(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a, b, group, a_token = self._create(client, admin_headers)
        b_token = login_as(client, "b", default_password("b"))
        settlement = client.post(
            "/api/v1/settlements",
            json={"payer_id": b["id"], "recipient_id": a["id"], "amount": "25.00"},
            headers=auth_headers(b_token),
        ).json()
        client.post(f"/api/v1/settlements/{settlement['id']}/confirm", headers=auth_headers(a_token))

        expense = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"][0]
        response = client.patch(
            f"/api/v1/expenses/{expense['id']}", json={"amount": "999.00"}, headers=auth_headers(a_token)
        )
        assert response.status_code == 400
        assert "settlement" in response.json()["message"].lower()

        # Non-balance-changing fields (title) can still be edited.
        response = client.patch(
            f"/api/v1/expenses/{expense['id']}",
            json={"title": "Still editable"},
            headers=auth_headers(a_token),
        )
        assert response.status_code == 200

    def test_delete_by_creator(self, client: TestClient, admin_headers: dict[str, str]):
        a, b, group, a_token = self._create(client, admin_headers)
        expense = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"][0]
        response = client.delete(f"/api/v1/expenses/{expense['id']}", headers=auth_headers(a_token))
        assert response.status_code == 204
        assert client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"] == []

    def test_delete_forbidden_for_other_member(self, client: TestClient, admin_headers: dict[str, str]):
        a, b, group, a_token = self._create(client, admin_headers)
        b_token = login_as(client, "b", default_password("b"))
        expense = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"][0]
        response = client.delete(f"/api/v1/expenses/{expense['id']}", headers=auth_headers(b_token))
        assert response.status_code == 403

    def test_duplicate_returns_draft_without_persisting(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a, b, group, a_token = self._create(client, admin_headers)
        expense = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"][0]
        response = client.post(
            f"/api/v1/expenses/{expense['id']}/duplicate", headers=auth_headers(a_token)
        )
        assert response.status_code == 200
        draft = response.json()
        assert "id" not in draft
        assert draft["title"] == expense["title"]
        assert draft["payers"] == []
        # Nothing new was persisted.
        assert len(client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"]) == 1


class TestListFilters:
    def test_filters_by_group_member_category_search_and_date(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        group = make_group(client, admin_headers, "Pair", [a["id"], b["id"]])
        a_token = login_as(client, "a", default_password("a"))
        category = client.post(
            "/api/v1/categories", json={"name": "Food"}, headers=admin_headers
        ).json()

        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Pizza night",
                "amount": "20.00",
                "expense_date": "2026-01-05",
                "category_id": category["id"],
                "tags": ["fun"],
                "payers": [{"user_id": a["id"], "amount": "20.00"}],
                "participant_ids": [a["id"], b["id"]],
            },
            headers=auth_headers(a_token),
        )
        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group["id"],
                "title": "Rent",
                "amount": "500.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "500.00"}],
                "participant_ids": [a["id"], b["id"]],
            },
            headers=auth_headers(a_token),
        )

        by_search = client.get(
            "/api/v1/expenses", params={"search": "pizza"}, headers=auth_headers(a_token)
        ).json()
        assert len(by_search["items"]) == 1 and by_search["items"][0]["title"] == "Pizza night"

        by_category = client.get(
            "/api/v1/expenses", params={"category_id": category["id"]}, headers=auth_headers(a_token)
        ).json()
        assert len(by_category["items"]) == 1

        by_tag = client.get(
            "/api/v1/expenses", params={"tag": "fun"}, headers=auth_headers(a_token)
        ).json()
        assert len(by_tag["items"]) == 1

        by_date = client.get(
            "/api/v1/expenses", params={"date_from": "2026-01-03"}, headers=auth_headers(a_token)
        ).json()
        assert len(by_date["items"]) == 1 and by_date["items"][0]["title"] == "Pizza night"

        newest_first = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"]
        assert [e["title"] for e in newest_first] == ["Pizza night", "Rent"]

    def test_pagination_cursor(self, client: TestClient, admin_headers: dict[str, str]):
        a = create_user(client, admin_headers, "a")
        group = make_group(client, admin_headers, "Solo", [a["id"]])
        a_token = login_as(client, "a", default_password("a"))
        for i in range(5):
            client.post(
                "/api/v1/expenses",
                json={
                    "group_id": group["id"],
                    "title": f"Expense {i}",
                    "amount": "1.00",
                    "expense_date": f"2026-01-0{i + 1}",
                    "payers": [{"user_id": a["id"], "amount": "1.00"}],
                    "participant_ids": [a["id"]],
                },
                headers=auth_headers(a_token),
            )
        page1 = client.get(
            "/api/v1/expenses", params={"limit": 2}, headers=auth_headers(a_token)
        ).json()
        assert len(page1["items"]) == 2
        assert page1["total"] == 5
        assert page1["next_cursor"] == 2

        page2 = client.get(
            "/api/v1/expenses",
            params={"limit": 2, "cursor": page1["next_cursor"]},
            headers=auth_headers(a_token),
        ).json()
        assert len(page2["items"]) == 2
        assert page2["next_cursor"] == 4

    def test_users_only_see_expenses_in_their_own_groups(
        self, client: TestClient, admin_headers: dict[str, str]
    ):
        a = create_user(client, admin_headers, "a")
        b = create_user(client, admin_headers, "b")
        group_a = make_group(client, admin_headers, "A-only", [a["id"]])
        group_b = make_group(client, admin_headers, "B-only", [b["id"]])
        a_token = login_as(client, "a", default_password("a"))
        b_token = login_as(client, "b", default_password("b"))
        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group_a["id"],
                "title": "A's expense",
                "amount": "1.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": a["id"], "amount": "1.00"}],
                "participant_ids": [a["id"]],
            },
            headers=auth_headers(a_token),
        )
        client.post(
            "/api/v1/expenses",
            json={
                "group_id": group_b["id"],
                "title": "B's expense",
                "amount": "1.00",
                "expense_date": "2026-01-01",
                "payers": [{"user_id": b["id"], "amount": "1.00"}],
                "participant_ids": [b["id"]],
            },
            headers=auth_headers(b_token),
        )
        a_view = client.get("/api/v1/expenses", headers=auth_headers(a_token)).json()["items"]
        assert [e["title"] for e in a_view] == ["A's expense"]
