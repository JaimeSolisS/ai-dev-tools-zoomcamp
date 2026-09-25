from fastapi import APIRouter, Response

from ..auth import CurrentUser, Principal, StoreDep
from ..models import Participant

router = APIRouter(prefix="/v1/sessions/{session_id}/participants", tags=["participants"])


@router.get("", response_model=list[Participant])
async def list_participants(session_id: str, principal: Principal, store: StoreDep):
    return store.list_participants(session_id)


@router.delete("/{participant_id}", status_code=204)
async def remove_participant(session_id: str, participant_id: str, user: CurrentUser, store: StoreDep):
    store.remove_participant(user, session_id, participant_id)
    return Response(status_code=204)
