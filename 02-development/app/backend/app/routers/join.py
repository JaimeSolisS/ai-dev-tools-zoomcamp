from fastapi import APIRouter

from ..auth import CallerDep, StoreDep
from ..models import JoinInfo, JoinInput, JoinResult

router = APIRouter(prefix="/v1/join", tags=["join"])


@router.get("/{token}", response_model=JoinInfo)
def get_join_info(token: str, store: StoreDep):
    return store.join_info(token)


@router.post("/{token}", response_model=JoinResult)
def join_session(token: str, body: JoinInput, caller: CallerDep, store: StoreDep):
    participant, credential = store.join(token, body.display_name, caller.user, caller.guest_credential)
    return JoinResult(
        session_id=participant.session_id,
        participant=participant,
        credential=credential,
    )
