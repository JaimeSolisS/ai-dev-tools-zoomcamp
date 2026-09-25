from fastapi import APIRouter, Response

from ..auth import CurrentUser, StoreDep
from ..models import CreatedGuestLink, CreateGuestLinkInput, GuestLink

router = APIRouter(prefix="/v1/sessions/{session_id}/guest-links", tags=["guest-links"])


@router.get("", response_model=list[GuestLink])
async def list_guest_links(session_id: str, user: CurrentUser, store: StoreDep):
    return store.list_links(user, session_id)


@router.post("", response_model=CreatedGuestLink, status_code=201)
async def create_guest_link(
    session_id: str, user: CurrentUser, store: StoreDep, body: CreateGuestLinkInput | None = None
):
    link, token = store.create_link(user, session_id, body or CreateGuestLinkInput())
    return CreatedGuestLink(link=GuestLink(**link.model_dump()), token=token)


@router.delete("/{link_id}", status_code=204)
async def revoke_guest_link(session_id: str, link_id: str, user: CurrentUser, store: StoreDep):
    store.revoke_link(user, session_id, link_id)
    return Response(status_code=204)
