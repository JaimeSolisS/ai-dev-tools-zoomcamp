import { describe, expect, it } from 'vitest';
import { computePermissions } from './permissions';

const live = { state: 'live' as const, candidateEditingEnabled: true };

describe('permission matrix', () => {
  it('matches the spec for a live session', () => {
    expect(computePermissions('owner', live)).toMatchObject({ canEdit: true, canShare: true, canStartOrEnd: true, canRemoveParticipants: true });
    expect(computePermissions('interviewer', live)).toMatchObject({ canEdit: true, canLockEditing: true, canShare: false, canStartOrEnd: false });
    expect(computePermissions('candidate', live)).toMatchObject({ canView: true, canEdit: true, canLockEditing: false });
    expect(computePermissions('observer', live)).toMatchObject({ canView: true, canEdit: false });
  });

  it('locks candidates only', () => {
    const locked = { ...live, candidateEditingEnabled: false };
    expect(computePermissions('candidate', locked).canEdit).toBe(false);
    expect(computePermissions('interviewer', locked).canEdit).toBe(true);
  });

  it('candidates cannot edit drafts; nobody edits ended sessions', () => {
    expect(computePermissions('candidate', { ...live, state: 'draft' }).canEdit).toBe(false);
    expect(computePermissions('owner', { ...live, state: 'draft' }).canEdit).toBe(true);
    for (const role of ['owner', 'interviewer', 'candidate', 'observer'] as const) {
      expect(computePermissions(role, { ...live, state: 'ended' }).canEdit).toBe(false);
    }
    expect(computePermissions('candidate', { ...live, state: 'ended' }).canView).toBe(false);
    expect(computePermissions('owner', { ...live, state: 'ended' }).canView).toBe(true);
  });
});
