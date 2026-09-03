# Shared Household Chores — MVP Plan

## 1. Goal

Build a simple MVP for managing shared household chores in a single household.

The tool should work for roommates, families, couples, or any shared household.

The MVP should prioritize simplicity over advanced automation, notifications, or customization.

---

## 2. Users and Roles

### Roles

The MVP has two roles:

- **Admin**
- **Member**

Custom roles and permissions are out of scope for the MVP.

### Household model

- A user belongs to one household in the MVP.
- The data model should be designed so multiple households per user can be supported later.
- A household name is not required in the MVP.

---

## 3. Authentication and Member Management

### Login

- Login with **username + password**.
- No email login.
- No invite links or invitation codes.

### Creating members

Admins create member accounts directly.

Required fields:

- Username
- Password
- Display name

For the MVP, user-facing username uniqueness rules do not need to be strict. Use internal IDs behind the scenes.

### Member management

Admins can:

- Create members
- View members
- Remove members

The admin screen should keep member management minimal.

When a member is removed:

- Remove/hide them from active members.
- Keep their historical records internally.
- Any unfinished chores assigned to them become **unassigned** automatically.

No member deactivation feature is required in the MVP.

Members cannot leave the household themselves.

### Passwords and profiles

- Members cannot change their own password in the MVP.
- Members cannot edit their profile in the MVP.

---

## 4. Chore Model

Each chore can include:

- Title
- Description
- Due date
- Category
- Assignee(s)
- Status

### Categories

Preset categories:

- Cleaning
- Kitchen
- Laundry
- Bathroom
- Bedroom
- Shopping
- Trash
- Pet Care
- Other

Categories are fixed for the MVP, but the data model should allow custom categories later.

### Priority

No priority field in the MVP.

### Attachments

No photos or file attachments in the MVP.

### Due time

Chores have a **due date only**.

No time-of-day field.

### Recurring chores

Recurring chores are **out of scope for the MVP**.

---

## 5. Chore Creation Rules

### Admin

Admins can create chores for:

- One member
- Multiple members
- No member (unassigned)

Admins may create chores only for **today or future dates**.

### Member

Members can create chores only for **themselves**.

Member-created chores:

- Become active immediately.
- Can only use today or future dates.
- Cannot be edited or deleted by the member after creation.

### New Chore form

Fields:

- Title
- Description
- Due date
- Assignee(s)
- Category

For members, the assignee is restricted to themselves.

---

## 6. Chore Assignment

### Multiple assignees

A chore can be assigned to multiple members.

All assignees are visible to household members.

If any assigned member marks the chore **Done**, the chore is considered Done for everyone.

### Unassigned chores

Admins can create chores with no assignee.

Unassigned chores:

- Are visible to everyone.
- Are clearly labeled **Unassigned**.
- Can be claimed by any member.
- Can be claimed directly from the chore detail popup.
- Stay **Pending** after being claimed.

Once claimed, a member cannot unclaim the chore. Only an admin can change the assignment.

---

## 7. Chore Status Lifecycle

Statuses:

- **Pending**
- **In progress**
- **Done**

`Skipped` is not part of the MVP.

### Member status permissions

Members can change the status of chores assigned to them:

- Pending → In progress
- Pending → Done
- In progress → Done
- Done → Pending / In progress

Members may reopen chores assigned to them.

For chores with multiple assignees, any assignee may reopen the chore.

### Admin status permissions

Admins can set any available status directly.

### Completion history and reopening

When a Done chore is reopened:

- Remove its previous completion record from the simple completion history.

The MVP intentionally avoids a full audit trail.

---

## 8. Editing and Deleting Chores

### Member permissions

Members cannot edit chores after creation.

Members cannot:

- Change title
- Change description
- Change due date
- Change category
- Change assignees
- Delete chores

They may only update the status of chores assigned to them.

### Admin permissions

Admins can edit unfinished chores.

Admins can change:

- Title
- Description
- Due date
- Category
- Assignee(s)
- Status

Admins may change assignees while the chore is In progress.

Admins may change overdue chores to a future due date.

Admins may edit title, description, and category while a chore is In progress.

### Done chores

Done chores are locked and cannot be edited.

### Deletion

No chore deletion in the MVP.

This applies to:

- Pending chores
- In-progress chores
- Completed chores

There is also no Cancelled status.

---

## 9. Overdue Behavior

A chore is overdue when:

- Its due date is before today, and
- Its status is not Done.

Overdue chores:

- Keep their existing status.
- Stay on their original due date.
- Display an **Overdue** label.
- Also appear in a dedicated overdue section.

Admins may change the due date of an overdue chore.

---

## 10. Calendar

The calendar is the primary interface and home screen.

After login, users go directly to the calendar.

### Views

Supported views:

- Month
- Week

Default view:

- Month

Users can toggle between Month and Week views.

Users can navigate to previous and future periods.

A dedicated **Today** button is not required.

### Calendar display

Chores appear based on **due date only**.

Calendar entries show:

- Chore title
- Assignee(s)
- Status

Status should be visually distinguishable.

Month and Week views use the same general layout, with Week view showing a larger version of the same presentation.

### Too many chores on one day

If a date contains too many chores:

- Show the first few chores.
- Show **+N more** for the remaining chores.

Clicking **+N more** opens a small popup listing all chores for that date.

### Chore detail popup

Clicking a chore opens a simple detail popup showing:

- Title
- Description
- Assignees
- Category
- Due date
- Status

Unassigned chores also show a **Claim** action to members.

---

## 11. Chore Visibility

All household members can see all chores on the calendar.

There are no calendar filters in the MVP.

Completed chores remain visible on the calendar.

There is no separate **My Chores** screen.

---

## 12. Admin Screen

The MVP includes a separate admin screen.

Its purpose is primarily member management.

Admin screen features:

- View members
- Create member
- Remove member

Chore management remains primarily in the calendar interface.

---

## 13. Completion History

The MVP includes a completion history visible to **everyone**.

### Format

- Simple chronological list
- Includes Done chores
- Shows the final completion date

Keep history intentionally minimal:

- Chore title
- Final completion date

Do not show:

- Original due date
- Who completed the chore
- Full status history
- Edit history
- Assignment history

If a chore is reopened, remove its prior completion record.

---

## 14. Notifications and Reminders

No notifications in the MVP.

This includes:

- No email notifications
- No push notifications
- No in-app notifications
- No due-date reminders

---

## 15. Search and Filtering

No search in the MVP.

No calendar filters in the MVP.

---

## 16. Explicitly Out of Scope

The following are intentionally excluded from the MVP:

- Recurring chores
- Invite links
- Email invitations
- Multiple households per user
- Custom roles
- Custom permissions
- Member self-registration
- Member password changes
- Password reset flows
- Profile editing
- Avatars
- Household profile/name
- Notifications
- Reminders
- Priority levels
- Chore comments
- Household announcements
- Attachments
- Photos
- Due times
- Search
- Calendar filters
- Chore deletion
- Chore cancellation
- Chore approval workflows
- Completion proof
- Full audit history
- Gamification
- Points
- Streaks
- Rankings
- Rewards
- Custom categories

---

## 17. Suggested MVP Data Model

### User

```text
User
- id
- username
- password_hash
- display_name
- role: admin | member
- is_active
- created_at
```

### Chore

```text
Chore
- id
- title
- description
- due_date
- category
- status: pending | in_progress | done
- created_by_user_id
- created_at
- updated_at
- completed_at (nullable)
```

### ChoreAssignee

Use a join table because a chore may have multiple assignees.

```text
ChoreAssignee
- chore_id
- user_id
- assigned_at
```

No rows in `ChoreAssignee` means the chore is unassigned.

### CompletionHistory

```text
CompletionHistory
- id
- chore_id
- completed_at
```

If the chore is reopened, delete its active completion-history record.

### Category

For the MVP, categories can initially be represented as an enum or seeded table.

A table is preferable if custom categories are expected later.

```text
Category
- id
- name
- is_system
```

---

## 18. MVP Navigation

Suggested navigation:

```text
Login
  ↓
Calendar
  ├── Month view
  ├── Week view
  ├── New Chore
  ├── Chore Details
  └── Completion History

Admin only
  └── Admin
       └── Members
            ├── Create Member
            └── Remove Member
```

---

## 19. MVP Success Criteria

The MVP is successful if a household can:

1. Log in with username and password.
2. Have an admin create and remove members.
3. Create one-time chores with due dates and categories.
4. Assign chores to one, multiple, or no members.
5. Let members claim unassigned chores.
6. Let members update assigned chores through Pending, In progress, and Done.
7. Let admins fully manage unfinished chores.
8. See all household chores in Month and Week calendar views.
9. Clearly identify overdue chores.
10. Review a simple chronological completion history.

The MVP should stop here before adding automation, notifications, recurring chores, advanced permissions, or gamification.
