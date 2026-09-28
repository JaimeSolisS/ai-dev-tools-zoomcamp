import type { InterviewSession, Permissions, Role } from './types';

/**
 * Permission matrix from the spec (§9). Shared by the UI (to disable controls)
 * and by backends (to authorize every request).
 */
export function computePermissions(role: Role, session: Pick<InterviewSession, 'state' | 'candidateEditingEnabled'>): Permissions {
  const isOwner = role === 'owner';
  const isStaff = role === 'owner' || role === 'interviewer';
  const open = session.state === 'draft' || session.state === 'live';

  let canEdit = false;
  if (isStaff) canEdit = open;
  else if (role === 'candidate') canEdit = session.state === 'live' && session.candidateEditingEnabled;

  return {
    canView: isStaff ? session.state !== 'archived' || isOwner : open,
    canEdit,
    canLockEditing: isStaff && open,
    canShare: isOwner && open,
    canRemoveParticipants: isOwner && open,
    canStartOrEnd: isOwner,
    canClearCanvas: isOwner && open,
    canEditSettings: isOwner,
  };
}
