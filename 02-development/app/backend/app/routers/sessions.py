from fastapi import APIRouter

from ..auth import CurrentUser, Principal, StoreDep
from ..models import CreateSessionInput, InterviewSession, SessionSummary, UpdateSessionInput

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
async def list_sessions(user: CurrentUser, store: StoreDep):
    return store.list_sessions(user)


@router.post("", response_model=InterviewSession, status_code=201)
async def create_session(body: CreateSessionInput, user: CurrentUser, store: StoreDep):
    return store.create_session(user, body)


@router.get("/{session_id}", response_model=InterviewSession)
async def get_session(session_id: str, principal: Principal, store: StoreDep):
    return store.get_session(session_id)


@router.patch("/{session_id}", response_model=InterviewSession)
async def update_session(session_id: str, body: UpdateSessionInput, principal: Principal, store: StoreDep):
    return store.update_session(principal, session_id, body)


@router.post("/{session_id}/start", response_model=InterviewSession)
async def start_session(session_id: str, user: CurrentUser, store: StoreDep):
    return store.start_session(user, session_id)


@router.post("/{session_id}/end", response_model=InterviewSession)
async def end_session(session_id: str, user: CurrentUser, store: StoreDep):
    return store.end_session(user, session_id)


@router.post("/{session_id}/reopen", response_model=InterviewSession)
async def reopen_session(session_id: str, user: CurrentUser, store: StoreDep):
    return store.reopen_session(user, session_id)


@router.post("/{session_id}/archive", response_model=InterviewSession)
async def archive_session(session_id: str, user: CurrentUser, store: StoreDep):
    return store.archive_session(user, session_id)


@router.post("/{session_id}/duplicate", response_model=InterviewSession, status_code=201)
async def duplicate_session(session_id: str, user: CurrentUser, store: StoreDep):
    return store.duplicate_session(user, session_id)
