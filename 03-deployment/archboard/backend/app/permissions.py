"""Permission matrix (spec §9). Mirrors `frontend/src/services/permissions.ts`."""

from .models import Permissions, Role, SessionState


def compute_permissions(role: Role, state: SessionState, candidate_editing_enabled: bool) -> Permissions:
    is_owner = role == "owner"
    is_staff = role in ("owner", "interviewer")
    is_open = state in ("draft", "live")

    if is_staff:
        can_edit = is_open
    elif role == "candidate":
        can_edit = state == "live" and candidate_editing_enabled
    else:
        can_edit = False

    return Permissions(
        can_view=(state != "archived" or is_owner) if is_staff else is_open,
        can_edit=can_edit,
        can_lock_editing=is_staff and is_open,
        can_share=is_owner and is_open,
        can_remove_participants=is_owner and is_open,
        can_start_or_end=is_owner,
        can_clear_canvas=is_owner and is_open,
        can_edit_settings=is_owner,
    )
