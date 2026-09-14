from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_repos, require_admin
from app.errors import bad_request, not_found
from app.models.domain import Category, User
from app.repositories.bundle import Repositories
from app.schemas.categories import CreateCategoryRequest, UpdateCategoryRequest
from app.services.identity import new_id

router = APIRouter(prefix="/categories")


@router.get("", response_model=list[Category])
def list_categories(
    group_id: str | None = None,
    current_user: User = Depends(get_current_user),
    repos: Repositories = Depends(get_repos),
) -> list[Category]:
    return [c for c in repos.categories.list() if c.group_id is None or c.group_id == group_id]


@router.post("", response_model=Category, status_code=201)
def create_category(
    body: CreateCategoryRequest,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> Category:
    if not body.name.strip():
        raise bad_request("Category name is required.")
    category = Category(
        id=new_id("cat"),
        name=body.name.strip(),
        group_id=body.group_id,
        created_at=datetime.now(UTC),
    )
    return repos.categories.create(category)


@router.patch("/{category_id}", response_model=Category)
def update_category(
    category_id: str,
    body: UpdateCategoryRequest,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> Category:
    category = repos.categories.get(category_id)
    if not category:
        raise not_found("Category not found.")
    if not body.name.strip():
        raise bad_request("Category name can't be empty.")
    category = category.model_copy(update={"name": body.name.strip()})
    return repos.categories.update(category)


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: str,
    _admin: User = Depends(require_admin),
    repos: Repositories = Depends(get_repos),
) -> None:
    category = repos.categories.get(category_id)
    if not category:
        raise not_found("Category not found.")
    in_use = any(e.category_id == category_id for e in repos.expenses.list())
    if in_use:
        raise bad_request("This category is used by existing expenses and can't be deleted.")
    repos.categories.delete(category_id)
