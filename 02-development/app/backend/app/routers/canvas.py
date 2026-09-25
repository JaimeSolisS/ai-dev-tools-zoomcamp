from fastapi import APIRouter, Response

from ..auth import CurrentUser, Principal, StoreDep
from ..models import CanvasSnapshotInfo, RoomAccess

router = APIRouter(prefix="/v1/sessions/{session_id}/canvas", tags=["canvas"])


@router.get("", response_model=RoomAccess)
async def open_room(session_id: str, principal: Principal, store: StoreDep):
    return store.open_room(principal)


@router.post("/clear", status_code=204)
async def clear_canvas(session_id: str, user: CurrentUser, store: StoreDep):
    store.clear_canvas(user, session_id)
    return Response(status_code=204)


@router.get("/snapshots", response_model=list[CanvasSnapshotInfo])
async def list_snapshots(session_id: str, user: CurrentUser, store: StoreDep):
    return store.list_snapshots(user, session_id)


@router.post("/snapshots/{snapshot_id}/restore", status_code=204)
async def restore_snapshot(session_id: str, snapshot_id: str, user: CurrentUser, store: StoreDep):
    store.restore_snapshot(user, session_id, snapshot_id)
    return Response(status_code=204)
