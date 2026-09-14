# Balancio — Product & Implementation Specification

> **Working product name:** Balancio  
> **Tagline:** Split expenses. Settle balances.

## 1. Purpose

Balancio is a general-purpose shared expense splitter for friends, households, couples, trips, and other small groups.

The MVP should make it easy to:

- Create and manage users and groups.
- Record shared expenses with one or more payers.
- Split expenses equally among selected participants.
- Calculate balances across users and groups.
- Suggest simplified global settlements.
- Record and confirm repayments.
- Record and confirm refunds.
- Keep the application simple enough to run locally with mock persistence while remaining database-agnostic for a later production database.

---

## 2. MVP Technology Stack

### Backend

- Python
- `uv` for Python dependency and environment management
- FastAPI
- Pydantic for request, response, and persisted-data validation
- JWT authentication
- SQLAlchemy + SQLite persistence for the MVP
- Repository abstraction so the database engine can later be swapped for PostgreSQL, MySQL, or another SQLAlchemy-supported database (via `DATABASE_URL`) without rewriting business rules
- `ruff` for linting/formatting
- Python type checking

### Frontend

- Node.js
- React
- Vite
- TypeScript
- Tailwind CSS
- React Router
- React state + Context only
- ESLint
- Prettier

### Testing

- Backend unit tests
- Backend API/integration tests
- Frontend component tests
- End-to-end browser tests

### Explicitly not required for the MVP

- Docker
- Deployment configuration
- CI implementation
- Database server
- Email infrastructure
- File/object storage

---

## 3. Product Roles

### 3.1 Regular User

A regular user can:

- Log in.
- Belong to multiple groups.
- View all expenses in groups they belong to.
- Add expenses to their groups.
- Edit or delete expenses they created, subject to settlement rules.
- Add refunds.
- Record settlements.
- Confirm or reject settlements involving them.
- Request reversal of confirmed settlements involving them.
- Comment on transactions they are involved in.
- View group balances.
- View global balances.
- Leave a group only when their relevant balance is zero.
- Change their password after the required first-login password change.
- Change and save their light/dark theme preference.

### 3.2 Global Admin

There is one global administrative role.

The admin is also a normal user and can participate in expenses and settlements.

The admin additionally can:

- Create users.
- Create groups.
- Add/remove users from groups.
- Reset user passwords.
- Force a user password reset.
- Deactivate users, but only when their global balance is zero.
- Manage global categories.
- Manage group-specific categories.
- Edit/delete any expense, subject to business rules.
- View all users, groups, balances, pending settlements, pending refunds, and basic system statistics.
- Access a dedicated **Admin** tab in the application's main navigation.

There is **no impersonation feature**.

---

## 4. Initial Setup

### 4.1 First Launch

If no global admin exists, the application shows an initial setup screen.

The setup screen creates the first admin account.

Required fields:

- Username
- Display name
- Password

Password minimum:

- 8 characters

### 4.2 Setup After Initialization

Once an admin exists:

- Normal users cannot access setup.
- The admin may continue to access setup-related settings through the Admin area.
- The initial-user creation flow must not accidentally create a second global admin unless the implementation explicitly supports that later.

---

## 5. Authentication

### 5.1 Login

Authentication uses:

- Username
- Password
- JWT access token

JWT lifetime:

- 8 hours

No refresh-token system is required for the MVP.

### 5.2 Password Lifecycle

When the admin creates a user:

1. The admin sets an initial temporary password.
2. The user logs in.
3. The user is forced to change the password before using the rest of the app.

### 5.3 Forgotten Password

There is no email-based or security-question-based self-service recovery.

Reset flow:

1. User asks the admin for a reset outside the application.
2. Admin generates a new temporary password.
3. User logs in using the temporary password.
4. User is required to change it.

The admin may also proactively force a password reset.

---

## 6. User Model

Each user contains at least:

- `id`
- `username`
- `display_name`
- `password_hash`
- `role`
- `is_active`
- `must_change_password`
- `theme`
- `created_at`
- `updated_at`

Theme values:

- `light`
- `dark`

No email or avatar is required.

---

## 7. Currency

Balancio uses one application-wide currency.

The currency is configured in backend configuration/environment settings.

Examples:

- `MXN`
- `USD`
- `EUR`

Rules:

- Users cannot choose a currency per expense.
- Groups cannot use different currencies.
- All balances, expenses, refunds, and settlements use the configured application currency.
- Currency values use exactly two decimal places.

Recommended configuration variable:

```env
APP_CURRENCY=MXN
```

All monetary calculations must use decimal arithmetic rather than binary floating point.

---

## 8. Groups

### 8.1 Group Creation

Only the global admin can create groups.

A group contains:

- `id`
- `name`
- `description` (optional)
- `member_ids`
- `status`
- `created_at`
- `updated_at`

Possible status values:

- `active`
- `archived`

### 8.2 Membership

A user may belong to multiple groups.

Membership in a group does **not** make the user responsible for every group expense.

A user only participates financially in an expense when explicitly selected as a participant for that expense.

### 8.3 Leaving or Removing Members

A user can leave a group only when their relevant balance is zero.

The admin can remove a user from a group only when that user's relevant balance is zero.

Historical expenses remain intact.

### 8.4 Archiving Groups

Groups are archived rather than deleted in normal operation.

A group can be archived only when all balances associated with the group are zero.

Archived groups are read-only.

---

## 9. Categories

Balancio supports:

- Default/global categories
- Custom group-specific categories

Examples:

- Groceries
- Rent
- Utilities
- Dining
- Travel
- Entertainment
- Transportation
- Other

Only the global admin can:

- Create global categories.
- Create group-specific categories.
- Edit categories.
- Delete categories when safe.

A group may use:

- Global categories
- Categories created specifically for that group

---

## 10. Tags

Expenses may contain free-form tags.

Examples:

- `vacation`
- `birthday`
- `family`
- `work`

Rules:

- Tags are not centrally managed.
- Users can type any tag.
- Tags can be used in expense search.

---

## 11. Expenses

### 11.1 Required Fields

An expense contains at least:

- `id`
- `group_id`
- `title`
- `amount`
- `expense_date`
- `category_id`
- `note` (optional)
- `tags`
- `created_by`
- `payers`
- `participant_ids`
- `created_at`
- `updated_at`

The title is required.

The expense date is required.

### 11.2 Participants

An expense may include:

- All group members
- Any selected subset of group members

Participants must be members of the group.

A newly added group member does not inherit prior expenses automatically.

An existing expense may later be edited to add or remove participants, subject to settlement constraints.

### 11.3 Equal Split Only

The MVP supports only equal splitting.

Example:

```text
Expense: $100.00
Participants: 3
Shares:
- $33.34
- $33.33
- $33.33
```

If the amount does not divide evenly:

- The backend assigns remainder cent(s) automatically.
- The final participant shares must sum exactly to the expense total.

The implementation should assign remainder cents deterministically so repeated calculations produce the same result.

### 11.4 Payers

An expense may have:

- One payer
- Multiple payers

Payer amounts must sum exactly to the total expense amount.

A payer:

- Must be a member of the group.
- Does **not** have to be a participant in the split.

Example:

Jaime may pay $300 for Ana and Carlos while owing none of the expense himself.

### 11.5 Editing Expenses

The expense creator may edit their expense.

The global admin may edit any expense.

Editable fields may include:

- Title
- Amount
- Date
- Category
- Note
- Tags
- Participants
- Payers
- Payer amounts

If the expense has related settlements and the proposed edit would change balances:

- Block the edit.
- Return a friendly explanation.

### 11.6 Deleting Expenses

The creator or global admin may delete an expense.

Deletion is permanent.

If settlements already exist:

- The expense may still be deleted.
- Existing settlements remain unchanged.
- Balances are recalculated.
- Any resulting overpayment becomes a credit.

### 11.7 Duplicating Expenses

Users can duplicate an existing expense.

Duplication copies:

- Title
- Category
- Participants
- Note
- Tags
- Total amount/structure as appropriate

Duplication resets:

- Expense date
- Payer amounts

The new expense must be reviewed before saving.

### 11.8 Expense Visibility

Every member of a group may view every expense in that group.

### 11.9 Expense Confirmation

Expenses do not require participant confirmation.

They affect balances immediately after creation.

### 11.10 Attachments

No receipts, images, PDFs, or other attachments are required in the MVP.

### 11.11 Recurring Expenses

Recurring expenses are out of scope.

### 11.12 Bulk Entry

Bulk expense entry/import is out of scope.

---

## 12. Expense Search and Browsing

Users can:

- Search expense text.
- Filter by group.
- Filter by date/date range.
- Filter by category.
- Filter by member.
- Filter by tags where useful.

Default ordering:

- Newest `expense_date` first.

Expense browsing uses infinite scroll.

Backend list endpoints should therefore support cursor- or page-based incremental loading even if the first implementation uses a simple offset internally.

---

## 13. Balance Model

Balancio maintains two important concepts:

### 13.1 Group Breakdown

Users can inspect the expense-derived balance relationships inside each group.

This provides context such as:

```text
Home
You owe Ana $300

Trip
Ana owes you $150
```

### 13.2 Global Balance

Balances are netted globally across all groups.

The dashboard shows the final person-to-person relationship.

Example:

```text
Home: You owe Ana $300
Trip: Ana owes you $150

Global:
You owe Ana $150
```

Users can see:

- Who they owe.
- Who owes them.
- Which groups contributed to the relationship.

All members of a group may view the complete group balance relationships, not just balances involving themselves.

---

## 14. Debt Simplification

Balancio automatically calculates simplified settlement suggestions.

Goal:

- Minimize the number of payments required to bring all global balances to zero.

Suggested settlements operate on global net balances, not individual group debts.

Example:

Instead of:

```text
Ana -> Jaime $20
Jaime -> Carlos $20
```

Balancio may suggest:

```text
Ana -> Carlos $20
```

Suggestions are advisory.

Users may also create custom settlements manually.

---

## 15. Settlements

A settlement represents a payment from one user to another.

Settlements are global and are not allocated to individual groups.

A settlement contains at least:

- `id`
- `payer_id`
- `recipient_id`
- `amount`
- `note` (optional)
- `status`
- `created_at`
- `updated_at`

Possible statuses:

- `pending`
- `confirmed`
- `rejected`
- `cancelled`
- `reversal_pending`
- `reversed`

### 15.1 Creating a Settlement

A user can create a settlement:

- From a suggested balance using **Settle up**
- Through a manual settlement form

Partial settlements are allowed.

Overpayments are allowed.

If a user owes $500 and pays $700:

- The extra $200 becomes a credit in the payer's favor after confirmation/current-balance rules are applied.

### 15.2 Settlement Confirmation

A settlement requires recipient confirmation.

Before confirmation:

- It is `pending`.

The payer may cancel a pending settlement.

The recipient may reject a pending settlement.

The payer may edit a pending settlement before confirmation.

### 15.3 Pending Settlement Balance Behavior

Pending settlements affect the application's **current balance immediately**.

The UI must show two balance concepts:

- **Current balance** — includes pending settlements.
- **Confirmed balance** — includes only confirmed settlements.

This distinction must be clearly labeled.

### 15.4 Confirmed Settlement Reversal

Either participant may request reversal of a confirmed settlement.

The reversal requires confirmation from the other participant.

Until confirmed:

- The reversal remains pending.

After confirmation:

- The settlement is treated as reversed.
- Balances are recalculated.

---

## 16. Refunds

Refunds are a dedicated transaction type.

They are standalone and do not need to reference an original expense.

A refund contains at least:

- `id`
- `group_id`
- `title`
- `amount`
- `participant_ids`
- `created_by`
- `status`
- `confirmations`
- `created_at`
- `updated_at`

### 16.1 Refund Creation

Any group member can create a refund.

Refunds use equal splitting among selected participants.

### 16.2 Refund Confirmation

Refunds require confirmation from **every affected participant**.

The UI must show confirmation status per person.

Example:

```text
Ana       Confirmed
Jaime     Confirmed
Carlos    Pending
```

### 16.3 Pending Refunds

Pending refunds do **not** affect balances.

A refund affects balances only after every affected participant confirms it.

---

## 17. Comments

Transactions may have a comments thread.

Comments are available on relevant:

- Expenses
- Settlements
- Refunds

Only users involved in the transaction may comment.

Comment model:

- `id`
- `transaction_type`
- `transaction_id`
- `author_id`
- `body`
- `created_at`
- `updated_at`

The comment author may:

- Edit their comment.
- Delete their comment.

Deletion is permanent.

The admin does not receive special comment-editing privileges for comments they did not author.

---

## 18. Transaction History Behavior

The MVP does not require a dedicated event/audit activity feed.

Do not build a system-level history such as:

```text
Ana edited expense
Jaime changed category
Admin removed member
```

However, the application's actual domain records remain visible according to their normal rules.

Settled/old transactions may be hidden or archived from the default main view.

Archived transactions:

- Remain searchable.
- Remain available in history views.
- Continue to affect balances as appropriate.

---

## 19. Dashboard

After login, users land on a dashboard.

The dashboard should provide a balanced overview.

Recommended order:

1. Current global balances
2. Confirmed global balances
3. Per-person balance breakdown
4. Suggested settlements
5. Pending settlements/refunds
6. Recent expenses/transactions
7. Groups

Do **not** add spending analytics such as:

- Monthly spending totals
- Charts by category
- Top spending groups

Those are outside the MVP.

---

## 20. Group Screen

Each group screen should include:

- Group name
- Optional description
- Member list
- Group balance breakdown
- Expense list
- Search/filter controls
- Add expense action
- Group-specific/global categories
- Pending refunds relevant to the group
- Archived/settled history access

All group members can view all group expenses.

---

## 21. Expense Creation UX

Expense creation should allow the user to:

1. Select group.
2. Enter title.
3. Enter amount.
4. Select date.
5. Select category.
6. Add optional note.
7. Add optional free-form tags.
8. Select one or more payers.
9. Enter payer amounts.
10. Select participants.
11. Review calculated equal shares.
12. Submit.

Participant selection:

- Show checkboxes for small groups.
- Provide member search for larger groups.

Payer total must equal expense total before submission.

---

## 22. Admin View

Admin functionality lives in an **Admin tab** within the normal application shell.

The admin dashboard includes:

- Users
- Groups
- Categories
- Global balances
- Pending settlements
- Pending refunds
- Basic system statistics
- Setup/settings access

### 22.1 User Management

Admin can:

- Create user.
- Set temporary password.
- Reset password.
- Force password change.
- Activate/deactivate when allowed.
- View memberships and balances.

A user can only be deactivated when their global balance is zero.

### 22.2 Group Management

Admin can:

- Create group.
- Edit name/description.
- Add members.
- Remove members when allowed.
- Archive group when all group balances are zero.

### 22.3 Destructive/Sensitive Actions

Admin actions that are destructive or sensitive require a confirmation dialog.

Examples:

- Delete expense.
- Reset password.
- Deactivate user.
- Remove user from group.
- Archive group.
- Delete category.

---

## 23. Dark Mode

Balancio supports:

- Light mode
- Dark mode

Users manually select their theme.

Theme preference is saved per user rather than only in browser storage.

---

## 24. Responsive Design

The application is a responsive web app.

It must work well on:

- Desktop browsers
- Tablets
- Mobile browsers

Desktop and mobile should expose the same core capabilities.

---

## 25. Error Handling

Users should see friendly, domain-specific error messages.

Examples:

```text
You can't remove this member until their balance is zero.
```

```text
This expense can't be edited because confirmed settlement activity depends on its current balance.
```

```text
Payer amounts must equal the total expense amount.
```

Do not expose:

- Stack traces
- Internal exception names
- Raw backend errors
- Sensitive implementation details

---

## 26. Backend Architecture

Keep the MVP backend deliberately simple.

Recommended structure:

```text
backend/
├── pyproject.toml
├── uv.lock
├── README.md
├── app/
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── dependencies.py
│   ├── models/
│   ├── schemas/
│   ├── repositories/
│   ├── routes/
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── groups.py
│   │   ├── expenses.py
│   │   ├── refunds.py
│   │   ├── settlements.py
│   │   ├── balances.py
│   │   ├── categories.py
│   │   ├── comments.py
│   │   └── admin.py
│   └── services/
│       └── balance_calculator.py
├── data/
│   └── balancio.db
└── tests/
```

The architectural preference is simple FastAPI rather than a highly abstract enterprise architecture.

However, balance calculation should be kept separate because it is core business logic and requires extensive testing.

Routes may call repositories directly for straightforward CRUD.

Complex financial rules should live in dedicated pure functions/services.

---

## 27. Repository Abstraction

Persistence must be database-agnostic.

Define repository interfaces/protocols for major entities.

Example conceptual interface:

```python
class ExpenseRepository(Protocol):
    def list(self, ...) -> list[Expense]: ...
    def get(self, expense_id: str) -> Expense | None: ...
    def create(self, expense: Expense) -> Expense: ...
    def update(self, expense: Expense) -> Expense: ...
    def delete(self, expense_id: str) -> None: ...
```

Initial implementation (SQLAlchemy-backed, SQLite by default):

```text
ExpenseRepository
UserRepository
GroupRepository
...
```

Later implementations might target a different SQLAlchemy-supported database:

```text
SqlAlchemyExpenseRepository
SqlAlchemyUserRepository
...
```

Business rules must not depend on JSON-specific behavior.

---

## 28. Database Persistence

Development data should survive backend restarts.

Use a local SQLite database file such as:

```text
backend/data/balancio.db
```

accessed through SQLAlchemy, configured via the `DATABASE_URL` environment
variable so a different SQLAlchemy-supported database can be swapped in
later without code changes.

Each major entity (`users`, `groups`, `categories`, `expenses`,
`settlements`, `refunds`, `comments`) maps to its own table. Small embedded
value objects that never need independent querying (e.g. an expense's
`payers`/`shares`, a refund's `confirmations`, or plain id/tag lists) may be
stored as JSON columns on the owning row rather than normalized into their
own tables.

Requirements:

- Business logic must interact only with the repository interfaces
  (`app/repositories/base.py`), never with SQLAlchemy sessions or ORM models
  directly, so persistence can change again later without touching business
  logic.
- Pydantic validates data at the domain-model boundary (both when it enters
  the repository layer and when it's read back out).
- Store timestamps in UTC.
- Store money using a safe, cent-accurate representation: numeric columns
  must use `Decimal`-backed types (never binary float), so values always
  reconcile to the cent.

---

## 29. Core Balance Calculation

The balance engine is the most important backend domain component.

### Inputs

- Expenses
- Confirmed refunds
- Settlements
- Settlement status
- Expense edits/deletions

### Expense Calculation

For each expense:

1. Credit each payer for the amount they paid.
2. Debit each participant for their equal share.
3. Net the amounts for each user.

### Global Balance

Sum each user's net position across all groups.

Then derive person-to-person obligations.

### Current vs Confirmed

Calculate at least two views:

#### Confirmed Balance

Includes:

- Expenses
- Confirmed refunds
- Confirmed settlements
- Confirmed reversals

Excludes:

- Pending settlements
- Pending refunds
- Pending reversals

#### Current Balance

Includes the same items plus pending settlements.

Pending refunds remain excluded.

---

## 30. Simplified Settlement Algorithm

The backend should expose a deterministic debt simplification function.

High-level approach:

1. Compute each user's global net balance.
2. Separate creditors and debtors.
3. Match debtors to creditors.
4. Produce settlement suggestions until all balances approach zero.

The algorithm should minimize the number of transfers where practical.

Financial calculations must always balance to zero at the cent level.

Deterministic ordering should be used for ties so tests are stable.

---

## 31. REST API

Suggested API prefix:

```text
/api/v1
```

### Authentication

```text
POST /api/v1/auth/setup
POST /api/v1/auth/login
POST /api/v1/auth/change-password
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

### Users

```text
GET    /api/v1/users
GET    /api/v1/users/{user_id}
POST   /api/v1/users
PATCH  /api/v1/users/{user_id}
POST   /api/v1/users/{user_id}/reset-password
POST   /api/v1/users/{user_id}/deactivate
POST   /api/v1/users/{user_id}/activate
```

Admin authorization applies where appropriate.

### Groups

```text
GET    /api/v1/groups
POST   /api/v1/groups
GET    /api/v1/groups/{group_id}
PATCH  /api/v1/groups/{group_id}
POST   /api/v1/groups/{group_id}/members
DELETE /api/v1/groups/{group_id}/members/{user_id}
POST   /api/v1/groups/{group_id}/leave
POST   /api/v1/groups/{group_id}/archive
```

### Categories

```text
GET    /api/v1/categories
POST   /api/v1/categories
PATCH  /api/v1/categories/{category_id}
DELETE /api/v1/categories/{category_id}
```

### Expenses

```text
GET    /api/v1/expenses
POST   /api/v1/expenses
GET    /api/v1/expenses/{expense_id}
PATCH  /api/v1/expenses/{expense_id}
DELETE /api/v1/expenses/{expense_id}
POST   /api/v1/expenses/{expense_id}/duplicate
```

List query parameters should support:

- `group_id`
- `member_id`
- `category_id`
- `date_from`
- `date_to`
- `search`
- `tag`
- pagination/cursor parameters

### Balances

```text
GET /api/v1/balances/me
GET /api/v1/balances/global
GET /api/v1/groups/{group_id}/balances
GET /api/v1/settlement-suggestions
```

### Settlements

```text
GET   /api/v1/settlements
POST  /api/v1/settlements
PATCH /api/v1/settlements/{settlement_id}
POST  /api/v1/settlements/{settlement_id}/confirm
POST  /api/v1/settlements/{settlement_id}/reject
POST  /api/v1/settlements/{settlement_id}/cancel
POST  /api/v1/settlements/{settlement_id}/request-reversal
POST  /api/v1/settlements/{settlement_id}/confirm-reversal
POST  /api/v1/settlements/{settlement_id}/reject-reversal
```

### Refunds

```text
GET  /api/v1/refunds
POST /api/v1/refunds
GET  /api/v1/refunds/{refund_id}
POST /api/v1/refunds/{refund_id}/confirm
```

### Comments

```text
GET    /api/v1/{transaction_type}/{transaction_id}/comments
POST   /api/v1/{transaction_type}/{transaction_id}/comments
PATCH  /api/v1/comments/{comment_id}
DELETE /api/v1/comments/{comment_id}
```

### Admin

```text
GET /api/v1/admin/overview
```

The final endpoint design may be adjusted during implementation, but domain boundaries and permissions should remain consistent with this specification.

---

## 32. Frontend Routing

Suggested routes:

```text
/login
/setup
/dashboard

/groups
/groups/:groupId
/groups/:groupId/expenses/new
/expenses/:expenseId
/expenses/:expenseId/edit

/settlements
/refunds
/history
/profile

/admin
```

The Admin entry appears only for the global admin.

---

## 33. Frontend Structure

Suggested structure:

```text
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── client.ts
│   ├── auth/
│   ├── components/
│   ├── contexts/
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── SetupPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── GroupsPage.tsx
│   │   ├── GroupPage.tsx
│   │   ├── ExpensePage.tsx
│   │   ├── ExpenseFormPage.tsx
│   │   ├── SettlementsPage.tsx
│   │   ├── RefundsPage.tsx
│   │   ├── HistoryPage.tsx
│   │   └── AdminPage.tsx
│   ├── types/
│   └── utils/
└── tests/
```

All backend calls should be centralized through the API client instead of calling `fetch()` directly throughout components.

---

## 34. Frontend State

Use:

- React local state for component-specific state.
- Context for authentication, current user, theme, and other small shared concerns.

Do not introduce Redux, Zustand, or TanStack Query for the MVP.

API fetching logic should still be structured so a dedicated server-state library can be introduced later without redesigning the app.

---

## 35. Navigation

Recommended primary navigation:

- Dashboard
- Groups
- Settlements
- History
- Admin — admin only
- Profile

On mobile, use a compact navigation pattern appropriate for small screens.

---

## 36. No Notifications

The MVP does not provide:

- Email notifications
- Push notifications
- In-app notification center

Pending items are surfaced naturally through dashboard and transaction screens.

---

## 37. No Export

The MVP does not provide:

- CSV export
- PDF export
- Spreadsheet export

---

## 38. No Multi-language Support

The MVP user interface is English only.

No i18n framework is required initially.

---

## 39. Testing Requirements

### 39.1 Backend Unit Tests

Prioritize tests for:

- Equal splits
- Remainder-cent allocation
- Multiple payers
- Payer not participating
- Expense edits
- Expense deletion
- Global netting
- Debt simplification
- Pending vs confirmed settlements
- Settlement confirmation
- Settlement rejection
- Settlement cancellation
- Settlement reversal
- Partial settlements
- Overpayment/credits
- Refund confirmations
- Group leave/remove restrictions
- User deactivation restrictions
- Group archive restrictions
- Permissions

### 39.2 API Tests

Test:

- Authentication
- Authorization
- Validation
- Happy paths
- Permission failures
- Invalid financial states
- Friendly API error payloads

### 39.3 Frontend Tests

Test key components and workflows such as:

- Login
- Forced password change
- Dashboard balances
- Expense form
- Multi-payer validation
- Participant selection
- Settlement confirmation
- Refund confirmation
- Admin controls
- Dark mode

### 39.4 End-to-End Tests

At minimum, cover:

#### Flow 1 — New user

1. Admin creates user.
2. User logs in with temporary password.
3. User changes password.
4. User reaches dashboard.

#### Flow 2 — Expense

1. Admin creates group.
2. Members are added.
3. Member creates multi-payer expense.
4. Balances update correctly.

#### Flow 3 — Settlement

1. User sees global debt.
2. User records partial payment.
3. Current balance updates.
4. Recipient confirms.
5. Confirmed balance updates.

#### Flow 4 — Refund

1. User creates refund.
2. Each affected participant confirms.
3. Balance remains unchanged until final confirmation.
4. Balance updates after final confirmation.

#### Flow 5 — Group lifecycle

1. User with non-zero balance cannot leave.
2. Group with non-zero balances cannot be archived.
3. After settlement, both actions succeed.

---

## 40. Local Development

### Backend

Expected workflow:

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

Exact commands may vary based on the final FastAPI CLI configuration.

### Frontend

Expected workflow:

```bash
cd frontend
npm install
npm run dev
```

No Docker is required.

---

## 41. Configuration

Suggested backend environment configuration:

```env
APP_NAME=Balancio
APP_CURRENCY=MXN
JWT_SECRET=change-me
JWT_EXPIRATION_HOURS=8
DATABASE_URL=sqlite:///./data/balancio.db
ENVIRONMENT=development
```

A `.env.example` should be committed.

Real secrets must not be committed.

---

## 42. README

Only a minimal root README is required for the MVP.

It should explain:

- What Balancio is.
- Prerequisites.
- How to install `uv` dependencies.
- How to run FastAPI.
- How to install Node dependencies.
- How to run React.
- Required environment variables.
- How to run tests.

FastAPI's automatically generated OpenAPI/Swagger documentation is sufficient for API exploration.

---

## 43. Out of Scope

The following should **not** be built for the initial MVP:

- Multiple currencies
- Currency conversion
- Recurring expenses
- Receipt/image attachments
- CSV/PDF exports
- Notifications
- Email
- Social login
- Invite links
- User registration
- Multiple admins unless deliberately added later
- Percentage splits
- Exact/custom splits
- Weighted shares
- Spending analytics/charts
- User avatars
- Multi-language support
- Transaction audit feed
- Docker
- CI pipelines
- Production deployment
- A production database server (Postgres/MySQL) - SQLite via SQLAlchemy is the MVP database
- Payment-provider integration
- Bank synchronization
- Automatic payment execution
- Bulk expense entry
- User impersonation

---

## 44. Recommended Implementation Phases

### Phase 1 — Project Foundation

Build:

- Monorepo/project folders
- FastAPI project with `uv`
- React/Vite/TypeScript/Tailwind project
- Environment configuration
- JSON repository abstraction
- Base Pydantic models
- API client
- Error response conventions

### Phase 2 — Authentication & Admin Bootstrap

Build:

- Setup flow
- Global admin creation
- Login
- JWT auth
- Password hashing
- Forced password change
- Password reset by admin
- Protected routes

### Phase 3 — Users, Groups & Categories

Build:

- User management
- Group creation/editing
- Membership management
- Global categories
- Group categories
- Admin tab

### Phase 4 — Expense Engine

Build:

- Expense creation
- Equal splits
- Multiple payers
- Participant selection
- Expense editing
- Expense deletion
- Duplicate expense
- Search/filter
- Infinite scrolling

### Phase 5 — Balance Engine

Build:

- Group balance calculation
- Global balance calculation
- Per-person breakdown
- Group contribution breakdown
- Current vs confirmed balances

This phase requires strong unit-test coverage before continuing.

### Phase 6 — Settlements

Build:

- Settlement suggestions
- Global settlement form
- Partial payment
- Overpayment credit
- Pending state
- Confirmation
- Rejection
- Cancellation
- Editing pending settlements
- Reversals

### Phase 7 — Refunds

Build:

- Standalone refunds
- Equal split
- Per-participant confirmation
- Pending/confirmed state
- Balance integration

### Phase 8 — Comments & History

Build:

- Transaction comments
- Edit/delete own comment
- Hide/archive settled transactions
- Search archived transactions

### Phase 9 — UX Polish

Build:

- Responsive layout
- Dark mode
- Saved theme
- Friendly empty states
- Confirmation dialogs
- Friendly validation/errors
- Loading states
- Mobile navigation

### Phase 10 — Full Test Pass

Complete:

- Backend unit tests
- API tests
- Frontend tests
- End-to-end tests
- Regression testing of financial calculations

---

## 45. MVP Acceptance Criteria

Balancio MVP is complete when all of the following are true:

- The application can initialize its first admin.
- Admin can create users and groups.
- New users must change temporary passwords.
- Users can log in with JWT authentication.
- Users can belong to multiple groups.
- Users can add expenses in their groups.
- Expenses support multiple payers.
- Expenses are equally split among selected participants.
- Payers do not have to be participants.
- All monetary values remain correct to the cent.
- Users can search/filter expense history.
- Global balances are calculated across all groups.
- Group contribution breakdowns remain visible.
- Settlement suggestions simplify global debts.
- Users can create partial or overpaying settlements.
- Pending settlements affect current but not confirmed balances.
- Recipients can confirm/reject settlements.
- Confirmed settlements can be reversed with counterparty confirmation.
- Users can create standalone refunds.
- Refunds affect balances only after all participants confirm.
- Users involved in a transaction can comment on it.
- Group members can view all expenses in the group.
- Users cannot leave groups with outstanding balances.
- Admin cannot remove/deactivate users with outstanding balances.
- Groups cannot be archived with outstanding balances.
- Admin has a full Admin tab.
- Dark mode works and is saved per user.
- UI works on desktop and mobile.
- JSON data persists across backend restarts.
- Business logic is not coupled to JSON persistence.
- Core flows have backend, frontend, API, and end-to-end tests.
- The project runs locally without Docker or deployment infrastructure.

---

## 46. Product Principle

When implementation choices are ambiguous, prefer:

1. **Financial correctness**
2. **Clear and predictable behavior**
3. **Simple user experience**
4. **Simple MVP implementation**
5. **Database-independent business logic**
6. **Extensibility only where it does not complicate the MVP**

The most important technical invariant is:

> The balance engine must always reconcile every transaction to the cent and produce deterministic results.
