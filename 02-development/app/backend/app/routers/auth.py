from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials

from ..auth import CurrentUser, StoreDep, bearer_scheme
from ..models import AuthResponse, LoginInput, MagicLinkRequest, MagicLinkRequestInput, User, VerifyMagicLinkInput

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.get("/me", response_model=User)
def get_current_user(user: CurrentUser):
    return user


@router.post("/magic-link", response_model=MagicLinkRequest, response_model_exclude_none=True)
def request_magic_link(body: MagicLinkRequestInput, store: StoreDep):
    token = store.request_magic_link(body.email)
    # A real deployment emails the link; development mode hands the token back instead.
    return MagicLinkRequest(dev_token=token if store.settings.dev_mode else None)


@router.post("/magic-link/verify", response_model=AuthResponse)
def verify_magic_link(body: VerifyMagicLinkInput, store: StoreDep):
    user = store.verify_magic_link(body.token)
    return AuthResponse(user=user, access_token=store.issue_access_token(user))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginInput, store: StoreDep):
    user = store.login(body.email, body.password)
    return AuthResponse(user=user, access_token=store.issue_access_token(user))


@router.post("/logout", status_code=204)
def sign_out(
    store: StoreDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
):
    if credentials is not None:
        store.revoke_access_token(credentials.credentials)
    return Response(status_code=204)
