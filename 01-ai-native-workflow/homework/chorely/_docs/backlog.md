# Chorely — MVP Backlog

Derived from `_docs/plan.md`. Ordered so each task builds on a working state.

## 1. Foundations

- [ ] **Data models**: `Household`, `User` (extend `AbstractUser` with `display_name`, `role`, `household` FK), `Category` (seeded, `is_system`), `Chore`, `ChoreAssignee` (join table), `CompletionHistory`. Design `User`/`Household` as a FK now (not M2M) so multi-household support can be added later without a schema rewrite.
- [ ] **Custom user model wiring**: set `AUTH_USER_MODEL`, register in admin, initial migration. Must be done before any other migration touches `User`.
- [ ] **Seed data**: management command or migration to create the fixed category list (Cleaning, Kitchen, Laundry, Bathroom, Bedroom, Shopping, Trash, Pet Care, Other).

## 2. Auth & Member Management

- [ ] Username + password login/logout (Django's built-in auth views).
- [ ] Admin-only "Members" screen: list active members.
- [ ] Admin: create member (username, password, display name), assigned `role=member` in the admin's household.
- [ ] Admin: remove member — hide from active list, keep row for history, and reassign their unfinished chores to unassigned (clear `ChoreAssignee` rows).
- [ ] Route guard/mixin restricting admin screens to `role=admin`.

## 3. Chore CRUD & Permissions

- [ ] Chore creation form (title, description, due date, category, assignee(s)) with role-based rules:
  - Admin: any member(s), multiple, or none; due date today or later.
  - Member: only self as assignee; due date today or later; chore active immediately.
- [ ] Chore edit (admin only, unfinished chores only): title, description, due date, category, assignees; enforce "Done chores are locked."
- [ ] Enforce no chore deletion anywhere (no delete view/route).
- [ ] Claim action for unassigned chores (any member, from chore detail popup) — stays Pending after claim; unclaim not permitted.

## 4. Status Lifecycle

- [ ] Status transition logic as a model method/service function encoding the allowed transitions per role (member: Pending↔In progress↔Done for their own chores; admin: any transition).
- [ ] On transition to Done: set `completed_at`, create `CompletionHistory` row.
- [ ] On reopening a Done chore (→ Pending/In progress): clear `completed_at`, delete the associated `CompletionHistory` row.
- [ ] "Done for everyone if any assignee marks Done" behavior for multi-assignee chores.

## 5. Overdue Handling

- [ ] Computed/annotated `is_overdue` (due_date < today and status != Done) — property or queryset annotation, not a stored field.
- [ ] Overdue label on chore display.
- [ ] Dedicated overdue section/query on the calendar page.

## 6. Calendar UI

- [ ] Month view: grid layout, chores per day showing title, assignee(s), status (visually distinct, e.g. color/icon).
- [ ] Week view: same data, larger per-day presentation.
- [ ] View toggle (Month/Week) + prev/next navigation.
- [ ] "+N more" per-day overflow with popup listing all chores for that date.
- [ ] Chore detail popup: title, description, assignees, category, due date, status, Claim action (members, unassigned only).
- [ ] Landing route: login → calendar (month view) by default.

## 7. Completion History

- [ ] Read-only chronological list view: chore title + final completion date only (no due date, assignee, or status history).
- [ ] Keep in sync with reopen logic from section 4.

## 8. Polish / Cross-cutting

- [ ] Permission tests: member cannot edit/delete chores, cannot assign others, cannot act on chores not assigned to them.
- [ ] Status-transition tests: valid/invalid transitions per role, completion-history create/remove on Done↔reopen.
- [ ] Overdue query/annotation tests.
- [ ] Basic templates/styling pass (no design system specified — keep minimal, consistent status colors).

## Explicitly deferred (out of scope per plan §16)

Recurring chores, invites, multi-household, custom roles/permissions, self-registration, password changes/reset, profile editing, notifications/reminders, priority, comments, attachments, due times, search/filters, deletion/cancellation, approval workflows, full audit trail, gamification, custom categories.
