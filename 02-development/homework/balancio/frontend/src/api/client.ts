// Centralized mock backend client.
//
// Every simulated network call funnels through this module. Nothing else in
// the app talks to storage or the domain model directly, so swapping this
// file for a real HTTP client later is a one-place change.

import type { Db } from "./db";
import { loadDb, saveDb, clearDb, emptyDb } from "./db";
import { buildSeedDb } from "./mockData";
import { ApiError } from "./errors";
import { newId } from "../utils/id";
import { toCents, fromCents } from "../utils/money";
import { computeGroupNet, computeGlobalNet, simplify, netToStrings } from "../utils/balanceCalculator";
import type {
  User,
  Role,
  Theme,
  Group,
  Category,
  Expense,
  Payer,
  Settlement,
  Refund,
  Comment,
  TransactionType,
  GroupBalances,
  GlobalBalances,
  PairBalance,
} from "../types";

const SESSION_KEY = "balancio_session_v1";
const NETWORK_DELAY_MS = 220;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), NETWORK_DELAY_MS));
}

// ---------------------------------------------------------------------------
// Storage bootstrap
// ---------------------------------------------------------------------------

let db: Db = loadDb() ?? emptyDb();
if (loadDb() === null) {
  saveDb(db);
}

function persist() {
  saveDb(db);
}

interface Session {
  userId: string;
  expiresAt: number;
}

function readSession(): Session | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as Session;
    if (session.expiresAt < Date.now()) return null;
    return session;
  } catch {
    return null;
  }
}

function writeSession(userId: string) {
  const session: Session = { userId, expiresAt: Date.now() + 8 * 60 * 60 * 1000 };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function currentUserOrThrow(): User {
  const session = readSession();
  if (!session) throw new ApiError("You need to log in to do that.");
  const user = db.users.find((u) => u.id === session.userId);
  if (!user) throw new ApiError("Your session is no longer valid. Please log in again.");
  return user;
}

function requireAdmin(): User {
  const user = currentUserOrThrow();
  if (user.role !== "admin") throw new ApiError("Only the admin can do that.");
  return user;
}

function sanitizeUser(user: User): User {
  return { ...user };
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function hasAdmin(): Promise<boolean> {
  return delay(db.users.some((u) => u.role === "admin"));
}

export async function setup(input: {
  username: string;
  display_name: string;
  password: string;
}): Promise<{ user: User }> {
  if (db.users.some((u) => u.role === "admin")) {
    throw new ApiError("Setup has already been completed.");
  }
  if (input.password.length < 8) {
    throw new ApiError("Password must be at least 8 characters.");
  }
  const username = input.username.trim().toLowerCase();
  if (!username) throw new ApiError("Username is required.");
  if (db.users.some((u) => u.username === username)) {
    throw new ApiError("That username is already taken.");
  }
  const now = new Date().toISOString();
  const user: User = {
    id: newId("usr"),
    username,
    display_name: input.display_name.trim() || username,
    role: "admin",
    is_active: true,
    must_change_password: false,
    theme: "light",
    created_at: now,
    updated_at: now,
  };
  db.users.push(user);
  db.passwords[user.id] = input.password;
  persist();
  writeSession(user.id);
  return delay({ user: sanitizeUser(user) });
}

export async function login(username: string, password: string): Promise<{ user: User }> {
  const user = db.users.find((u) => u.username === username.trim().toLowerCase());
  if (!user || db.passwords[user.id] !== password) {
    throw new ApiError("Incorrect username or password.");
  }
  if (!user.is_active) {
    throw new ApiError("This account has been deactivated. Contact your admin.");
  }
  writeSession(user.id);
  return delay({ user: sanitizeUser(user) });
}

export async function logout(): Promise<void> {
  clearSession();
  return delay(undefined);
}

export async function me(): Promise<User | null> {
  const session = readSession();
  if (!session) return delay(null);
  const user = db.users.find((u) => u.id === session.userId) ?? null;
  return delay(user ? sanitizeUser(user) : null);
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<User> {
  const user = currentUserOrThrow();
  if (db.passwords[user.id] !== oldPassword) {
    throw new ApiError("Current password is incorrect.");
  }
  if (newPassword.length < 8) {
    throw new ApiError("New password must be at least 8 characters.");
  }
  db.passwords[user.id] = newPassword;
  user.must_change_password = false;
  user.updated_at = new Date().toISOString();
  persist();
  return delay(sanitizeUser(user));
}

export async function updateMyTheme(theme: Theme): Promise<User> {
  const user = currentUserOrThrow();
  user.theme = theme;
  user.updated_at = new Date().toISOString();
  persist();
  return delay(sanitizeUser(user));
}

// ---------------------------------------------------------------------------
// Users (admin)
// ---------------------------------------------------------------------------

export async function listUsers(): Promise<User[]> {
  currentUserOrThrow();
  return delay(db.users.map(sanitizeUser));
}

export async function getUser(userId: string): Promise<User> {
  currentUserOrThrow();
  const user = db.users.find((u) => u.id === userId);
  if (!user) throw new ApiError("User not found.");
  return delay(sanitizeUser(user));
}

export async function createUser(input: {
  username: string;
  display_name: string;
  temporary_password: string;
  role?: Role;
}): Promise<User> {
  requireAdmin();
  const username = input.username.trim().toLowerCase();
  if (!username) throw new ApiError("Username is required.");
  if (db.users.some((u) => u.username === username)) {
    throw new ApiError("That username is already taken.");
  }
  if (input.temporary_password.length < 8) {
    throw new ApiError("Temporary password must be at least 8 characters.");
  }
  if (input.role === "admin") {
    throw new ApiError("Balancio supports only one global admin for now.");
  }
  const now = new Date().toISOString();
  const user: User = {
    id: newId("usr"),
    username,
    display_name: input.display_name.trim() || username,
    role: "user",
    is_active: true,
    must_change_password: true,
    theme: "light",
    created_at: now,
    updated_at: now,
  };
  db.users.push(user);
  db.passwords[user.id] = input.temporary_password;
  persist();
  return delay(sanitizeUser(user));
}

export async function updateUser(userId: string, patch: { display_name?: string }): Promise<User> {
  const actor = currentUserOrThrow();
  const user = db.users.find((u) => u.id === userId);
  if (!user) throw new ApiError("User not found.");
  if (actor.role !== "admin" && actor.id !== userId) {
    throw new ApiError("You can only edit your own profile.");
  }
  if (patch.display_name !== undefined) {
    if (!patch.display_name.trim()) throw new ApiError("Display name can't be empty.");
    user.display_name = patch.display_name.trim();
  }
  user.updated_at = new Date().toISOString();
  persist();
  return delay(sanitizeUser(user));
}

export async function resetPassword(userId: string, newTemporaryPassword: string): Promise<void> {
  requireAdmin();
  const user = db.users.find((u) => u.id === userId);
  if (!user) throw new ApiError("User not found.");
  if (newTemporaryPassword.length < 8) {
    throw new ApiError("Temporary password must be at least 8 characters.");
  }
  db.passwords[user.id] = newTemporaryPassword;
  user.must_change_password = true;
  user.updated_at = new Date().toISOString();
  persist();
  return delay(undefined);
}

export async function forcePasswordChange(userId: string): Promise<void> {
  requireAdmin();
  const user = db.users.find((u) => u.id === userId);
  if (!user) throw new ApiError("User not found.");
  user.must_change_password = true;
  user.updated_at = new Date().toISOString();
  persist();
  return delay(undefined);
}

function userGlobalBalanceCents(userId: string): number {
  const net = computeGlobalNet(db.expenses, db.refunds, db.settlements, true);
  return net[userId] ?? 0;
}

export async function deactivateUser(userId: string): Promise<User> {
  requireAdmin();
  const user = db.users.find((u) => u.id === userId);
  if (!user) throw new ApiError("User not found.");
  if (userGlobalBalanceCents(userId) !== 0) {
    throw new ApiError("You can't deactivate this user until their global balance is zero.");
  }
  user.is_active = false;
  user.updated_at = new Date().toISOString();
  persist();
  return delay(sanitizeUser(user));
}

export async function activateUser(userId: string): Promise<User> {
  requireAdmin();
  const user = db.users.find((u) => u.id === userId);
  if (!user) throw new ApiError("User not found.");
  user.is_active = true;
  user.updated_at = new Date().toISOString();
  persist();
  return delay(sanitizeUser(user));
}

// ---------------------------------------------------------------------------
// Groups
// ---------------------------------------------------------------------------

export async function listGroups(): Promise<Group[]> {
  const actor = currentUserOrThrow();
  if (actor.role === "admin") return delay([...db.groups]);
  return delay(db.groups.filter((g) => g.member_ids.includes(actor.id)));
}

export async function getGroup(groupId: string): Promise<Group> {
  const actor = currentUserOrThrow();
  const group = db.groups.find((g) => g.id === groupId);
  if (!group) throw new ApiError("Group not found.");
  if (actor.role !== "admin" && !group.member_ids.includes(actor.id)) {
    throw new ApiError("You are not a member of this group.");
  }
  return delay(group);
}

export async function createGroup(input: {
  name: string;
  description?: string;
  member_ids: string[];
}): Promise<Group> {
  requireAdmin();
  if (!input.name.trim()) throw new ApiError("Group name is required.");
  const now = new Date().toISOString();
  const group: Group = {
    id: newId("grp"),
    name: input.name.trim(),
    description: input.description?.trim() || undefined,
    member_ids: Array.from(new Set(input.member_ids)),
    status: "active",
    created_at: now,
    updated_at: now,
  };
  db.groups.push(group);
  persist();
  return delay(group);
}

export async function updateGroup(
  groupId: string,
  patch: { name?: string; description?: string },
): Promise<Group> {
  requireAdmin();
  const group = db.groups.find((g) => g.id === groupId);
  if (!group) throw new ApiError("Group not found.");
  if (patch.name !== undefined) {
    if (!patch.name.trim()) throw new ApiError("Group name can't be empty.");
    group.name = patch.name.trim();
  }
  if (patch.description !== undefined) group.description = patch.description.trim() || undefined;
  group.updated_at = new Date().toISOString();
  persist();
  return delay(group);
}

export async function addGroupMember(groupId: string, userId: string): Promise<Group> {
  requireAdmin();
  const group = db.groups.find((g) => g.id === groupId);
  if (!group) throw new ApiError("Group not found.");
  if (group.status === "archived") throw new ApiError("Archived groups are read-only.");
  if (!group.member_ids.includes(userId)) group.member_ids.push(userId);
  group.updated_at = new Date().toISOString();
  persist();
  return delay(group);
}

function groupRelevantBalanceCents(groupId: string, userId: string): number {
  const net = computeGroupNet(groupId, db.expenses, db.refunds);
  return net[userId] ?? 0;
}

export async function removeGroupMember(groupId: string, userId: string): Promise<Group> {
  requireAdmin();
  const group = db.groups.find((g) => g.id === groupId);
  if (!group) throw new ApiError("Group not found.");
  if (groupRelevantBalanceCents(groupId, userId) !== 0) {
    throw new ApiError("You can't remove this member until their balance in this group is zero.");
  }
  group.member_ids = group.member_ids.filter((id) => id !== userId);
  group.updated_at = new Date().toISOString();
  persist();
  return delay(group);
}

export async function leaveGroup(groupId: string): Promise<Group> {
  const actor = currentUserOrThrow();
  const group = db.groups.find((g) => g.id === groupId);
  if (!group) throw new ApiError("Group not found.");
  if (groupRelevantBalanceCents(groupId, actor.id) !== 0) {
    throw new ApiError("You can't leave this group until your balance here is zero.");
  }
  group.member_ids = group.member_ids.filter((id) => id !== actor.id);
  group.updated_at = new Date().toISOString();
  persist();
  return delay(group);
}

export async function archiveGroup(groupId: string): Promise<Group> {
  requireAdmin();
  const group = db.groups.find((g) => g.id === groupId);
  if (!group) throw new ApiError("Group not found.");
  const net = computeGroupNet(groupId, db.expenses, db.refunds);
  const nonZero = Object.values(net).some((v) => v !== 0);
  if (nonZero) throw new ApiError("This group can't be archived until all balances are zero.");
  group.status = "archived";
  group.updated_at = new Date().toISOString();
  persist();
  return delay(group);
}

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

export async function listCategories(groupId?: string): Promise<Category[]> {
  currentUserOrThrow();
  return delay(db.categories.filter((c) => c.group_id === null || c.group_id === groupId));
}

export async function createCategory(input: { name: string; group_id: string | null }): Promise<Category> {
  requireAdmin();
  if (!input.name.trim()) throw new ApiError("Category name is required.");
  const category: Category = {
    id: newId("cat"),
    name: input.name.trim(),
    group_id: input.group_id,
    created_at: new Date().toISOString(),
  };
  db.categories.push(category);
  persist();
  return delay(category);
}

export async function updateCategory(categoryId: string, patch: { name: string }): Promise<Category> {
  requireAdmin();
  const category = db.categories.find((c) => c.id === categoryId);
  if (!category) throw new ApiError("Category not found.");
  if (!patch.name.trim()) throw new ApiError("Category name can't be empty.");
  category.name = patch.name.trim();
  persist();
  return delay(category);
}

export async function deleteCategory(categoryId: string): Promise<void> {
  requireAdmin();
  const inUse = db.expenses.some((e) => e.category_id === categoryId);
  if (inUse) throw new ApiError("This category is used by existing expenses and can't be deleted.");
  db.categories = db.categories.filter((c) => c.id !== categoryId);
  persist();
  return delay(undefined);
}

// ---------------------------------------------------------------------------
// Expenses
// ---------------------------------------------------------------------------

export interface ExpenseFilters {
  group_id?: string;
  member_id?: string;
  category_id?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  tag?: string;
  cursor?: number;
  limit?: number;
}

export interface Page<T> {
  items: T[];
  next_cursor: number | null;
  total: number;
}

function assertGroupAccess(groupId: string, actor: User) {
  const group = db.groups.find((g) => g.id === groupId);
  if (!group) throw new ApiError("Group not found.");
  if (actor.role !== "admin" && !group.member_ids.includes(actor.id)) {
    throw new ApiError("You are not a member of this group.");
  }
  return group;
}

export async function listExpenses(filters: ExpenseFilters = {}): Promise<Page<Expense>> {
  const actor = currentUserOrThrow();
  const visibleGroupIds = new Set(
    actor.role === "admin"
      ? db.groups.map((g) => g.id)
      : db.groups.filter((g) => g.member_ids.includes(actor.id)).map((g) => g.id),
  );
  let items = db.expenses.filter((e) => visibleGroupIds.has(e.group_id));
  if (filters.group_id) items = items.filter((e) => e.group_id === filters.group_id);
  if (filters.member_id) {
    items = items.filter(
      (e) =>
        e.participant_ids.includes(filters.member_id!) ||
        e.payers.some((p) => p.user_id === filters.member_id),
    );
  }
  if (filters.category_id) items = items.filter((e) => e.category_id === filters.category_id);
  if (filters.date_from) items = items.filter((e) => e.expense_date >= filters.date_from!);
  if (filters.date_to) items = items.filter((e) => e.expense_date <= filters.date_to!);
  if (filters.tag) items = items.filter((e) => e.tags.includes(filters.tag!));
  if (filters.search) {
    const q = filters.search.toLowerCase();
    items = items.filter(
      (e) => e.title.toLowerCase().includes(q) || (e.note ?? "").toLowerCase().includes(q),
    );
  }
  items = [...items].sort((a, b) =>
    a.expense_date < b.expense_date
      ? 1
      : a.expense_date > b.expense_date
        ? -1
        : b.created_at.localeCompare(a.created_at),
  );

  const total = items.length;
  const cursor = filters.cursor ?? 0;
  const limit = filters.limit ?? 20;
  const page = items.slice(cursor, cursor + limit);
  const next_cursor = cursor + limit < total ? cursor + limit : null;
  return delay({ items: page, next_cursor, total });
}

export async function getExpense(expenseId: string): Promise<Expense> {
  const actor = currentUserOrThrow();
  const expense = db.expenses.find((e) => e.id === expenseId);
  if (!expense) throw new ApiError("Expense not found.");
  assertGroupAccess(expense.group_id, actor);
  return delay(expense);
}

function validatePayersAndShares(amount: string, payers: Payer[], participantIds: string[]) {
  const totalCents = toCents(amount);
  if (totalCents <= 0) throw new ApiError("Expense amount must be greater than zero.");
  const payerSum = payers.reduce((sum, p) => sum + toCents(p.amount), 0);
  if (payerSum !== totalCents) {
    throw new ApiError("Payer amounts must equal the total expense amount.");
  }
  if (participantIds.length === 0) {
    throw new ApiError("Select at least one participant.");
  }
  if (payers.length === 0) {
    throw new ApiError("Select at least one payer.");
  }
}

export interface ExpenseInput {
  group_id: string;
  title: string;
  amount: string;
  expense_date: string;
  category_id: string | null;
  note?: string;
  tags: string[];
  payers: Payer[];
  participant_ids: string[];
}

export async function createExpense(input: ExpenseInput): Promise<Expense> {
  const actor = currentUserOrThrow();
  const group = assertGroupAccess(input.group_id, actor);
  if (group.status === "archived") throw new ApiError("This group is archived and read-only.");
  if (!input.title.trim()) throw new ApiError("Title is required.");
  if (!input.expense_date) throw new ApiError("Expense date is required.");
  const nonMemberPayer = input.payers.find((p) => !group.member_ids.includes(p.user_id));
  if (nonMemberPayer) throw new ApiError("Payers must be members of the group.");
  const nonMemberParticipant = input.participant_ids.find((id) => !group.member_ids.includes(id));
  if (nonMemberParticipant) throw new ApiError("Participants must be members of the group.");
  validatePayersAndShares(input.amount, input.payers, input.participant_ids);

  const sharesCents = splitCents(toCents(input.amount), input.participant_ids);
  const now = new Date().toISOString();
  const expense: Expense = {
    id: newId("exp"),
    group_id: input.group_id,
    title: input.title.trim(),
    amount: input.amount,
    expense_date: input.expense_date,
    category_id: input.category_id,
    note: input.note?.trim() || undefined,
    tags: input.tags,
    created_by: actor.id,
    payers: input.payers,
    participant_ids: input.participant_ids,
    shares: input.participant_ids.map((user_id) => ({
      user_id,
      amount: fromCents(sharesCents.get(user_id) ?? 0),
    })),
    created_at: now,
    updated_at: now,
  };
  db.expenses.push(expense);
  persist();
  return delay(expense);
}

function splitCents(totalCents: number, order: string[]): Map<string, number> {
  const n = order.length;
  const base = Math.floor(totalCents / n);
  const remainder = totalCents - base * n;
  const sorted = [...order].sort();
  const result = new Map<string, number>();
  sorted.forEach((id, i) => result.set(id, base + (i < remainder ? 1 : 0)));
  return result;
}

function expenseHasRelatedConfirmedSettlementActivity(): boolean {
  // The MVP settles debts globally rather than per-expense, so there is no
  // direct expense/settlement link. As a conservative, spec-friendly proxy we
  // block balance-changing edits whenever *any* settlement has already been
  // confirmed, since that confirmation locked in a snapshot of the balances.
  return db.settlements.some((s) => s.status === "confirmed" || s.status === "reversal_pending");
}

export async function updateExpense(expenseId: string, patch: Partial<ExpenseInput>): Promise<Expense> {
  const actor = currentUserOrThrow();
  const expense = db.expenses.find((e) => e.id === expenseId);
  if (!expense) throw new ApiError("Expense not found.");
  const group = assertGroupAccess(expense.group_id, actor);
  if (group.status === "archived") throw new ApiError("This group is archived and read-only.");
  if (actor.role !== "admin" && actor.id !== expense.created_by) {
    throw new ApiError("Only the person who created this expense (or the admin) can edit it.");
  }

  const nextAmount = patch.amount ?? expense.amount;
  const nextPayers = patch.payers ?? expense.payers;
  const nextParticipants = patch.participant_ids ?? expense.participant_ids;
  const changesBalance =
    nextAmount !== expense.amount ||
    JSON.stringify(nextPayers) !== JSON.stringify(expense.payers) ||
    JSON.stringify([...nextParticipants].sort()) !== JSON.stringify([...expense.participant_ids].sort());

  if (changesBalance && expenseHasRelatedConfirmedSettlementActivity()) {
    throw new ApiError(
      "This expense can't be edited because confirmed settlement activity depends on its current balance.",
    );
  }

  if (patch.payers || patch.participant_ids || patch.amount) {
    validatePayersAndShares(nextAmount, nextPayers, nextParticipants);
    const nonMemberPayer = nextPayers.find((p) => !group.member_ids.includes(p.user_id));
    if (nonMemberPayer) throw new ApiError("Payers must be members of the group.");
    const nonMemberParticipant = nextParticipants.find((id) => !group.member_ids.includes(id));
    if (nonMemberParticipant) throw new ApiError("Participants must be members of the group.");
  }

  if (patch.title !== undefined) expense.title = patch.title.trim();
  if (patch.amount !== undefined) expense.amount = patch.amount;
  if (patch.expense_date !== undefined) expense.expense_date = patch.expense_date;
  if (patch.category_id !== undefined) expense.category_id = patch.category_id;
  if (patch.note !== undefined) expense.note = patch.note.trim() || undefined;
  if (patch.tags !== undefined) expense.tags = patch.tags;
  if (patch.payers !== undefined) expense.payers = patch.payers;
  if (patch.participant_ids !== undefined) expense.participant_ids = patch.participant_ids;

  const sharesCents = splitCents(toCents(expense.amount), expense.participant_ids);
  expense.shares = expense.participant_ids.map((user_id) => ({
    user_id,
    amount: fromCents(sharesCents.get(user_id) ?? 0),
  }));
  expense.updated_at = new Date().toISOString();
  persist();
  return delay(expense);
}

export async function deleteExpense(expenseId: string): Promise<void> {
  const actor = currentUserOrThrow();
  const expense = db.expenses.find((e) => e.id === expenseId);
  if (!expense) throw new ApiError("Expense not found.");
  assertGroupAccess(expense.group_id, actor);
  if (actor.role !== "admin" && actor.id !== expense.created_by) {
    throw new ApiError("Only the person who created this expense (or the admin) can delete it.");
  }
  db.expenses = db.expenses.filter((e) => e.id !== expenseId);
  db.comments = db.comments.filter(
    (c) => !(c.transaction_type === "expense" && c.transaction_id === expenseId),
  );
  persist();
  return delay(undefined);
}

export async function duplicateExpense(expenseId: string): Promise<ExpenseInput> {
  const actor = currentUserOrThrow();
  const expense = db.expenses.find((e) => e.id === expenseId);
  if (!expense) throw new ApiError("Expense not found.");
  assertGroupAccess(expense.group_id, actor);
  return delay({
    group_id: expense.group_id,
    title: expense.title,
    amount: expense.amount,
    expense_date: new Date().toISOString().slice(0, 10),
    category_id: expense.category_id,
    note: expense.note,
    tags: [...expense.tags],
    payers: [],
    participant_ids: [...expense.participant_ids],
  });
}

// ---------------------------------------------------------------------------
// Balances
// ---------------------------------------------------------------------------

export async function getGroupBalances(groupId: string): Promise<GroupBalances> {
  const actor = currentUserOrThrow();
  assertGroupAccess(groupId, actor);
  const net = computeGroupNet(groupId, db.expenses, db.refunds);
  return delay({ group_id: groupId, net: netToStrings(net), pairs: simplify(net) });
}

export async function getGlobalBalances(): Promise<GlobalBalances> {
  currentUserOrThrow();
  const confirmedNet = computeGlobalNet(db.expenses, db.refunds, db.settlements, false);
  const currentNet = computeGlobalNet(db.expenses, db.refunds, db.settlements, true);

  const contributions: Record<string, string[]> = {};
  for (const group of db.groups) {
    const groupNet = computeGroupNet(group.id, db.expenses, db.refunds);
    for (const pair of simplify(groupNet)) {
      const key = `${pair.from_user_id}:${pair.to_user_id}`;
      if (!contributions[key]) contributions[key] = [];
      contributions[key].push(group.id);
    }
  }

  return delay({
    current: { net: netToStrings(currentNet), pairs: simplify(currentNet) },
    confirmed: { net: netToStrings(confirmedNet), pairs: simplify(confirmedNet) },
    contributions,
  });
}

export async function getMyBalances(): Promise<GlobalBalances> {
  return getGlobalBalances();
}

export async function getSettlementSuggestions(): Promise<PairBalance[]> {
  currentUserOrThrow();
  const net = computeGlobalNet(db.expenses, db.refunds, db.settlements, true);
  return delay(simplify(net));
}

// ---------------------------------------------------------------------------
// Settlements
// ---------------------------------------------------------------------------

export async function listSettlements(): Promise<Settlement[]> {
  currentUserOrThrow();
  return delay([...db.settlements].sort((a, b) => b.created_at.localeCompare(a.created_at)));
}

export async function createSettlement(input: {
  payer_id: string;
  recipient_id: string;
  amount: string;
  note?: string;
}): Promise<Settlement> {
  currentUserOrThrow();
  if (input.payer_id === input.recipient_id)
    throw new ApiError("Payer and recipient must be different people.");
  if (toCents(input.amount) <= 0) throw new ApiError("Settlement amount must be greater than zero.");
  const now = new Date().toISOString();
  const settlement: Settlement = {
    id: newId("stl"),
    payer_id: input.payer_id,
    recipient_id: input.recipient_id,
    amount: input.amount,
    note: input.note?.trim() || undefined,
    status: "pending",
    created_at: now,
    updated_at: now,
  };
  db.settlements.push(settlement);
  persist();
  return delay(settlement);
}

function findSettlement(id: string): Settlement {
  const settlement = db.settlements.find((s) => s.id === id);
  if (!settlement) throw new ApiError("Settlement not found.");
  return settlement;
}

export async function updateSettlement(
  settlementId: string,
  patch: { amount?: string; note?: string },
): Promise<Settlement> {
  const actor = currentUserOrThrow();
  const settlement = findSettlement(settlementId);
  if (settlement.payer_id !== actor.id && actor.role !== "admin") {
    throw new ApiError("Only the payer can edit this settlement.");
  }
  if (settlement.status !== "pending") {
    throw new ApiError("Only pending settlements can be edited.");
  }
  if (patch.amount !== undefined) {
    if (toCents(patch.amount) <= 0) throw new ApiError("Settlement amount must be greater than zero.");
    settlement.amount = patch.amount;
  }
  if (patch.note !== undefined) settlement.note = patch.note.trim() || undefined;
  settlement.updated_at = new Date().toISOString();
  persist();
  return delay(settlement);
}

export async function confirmSettlement(settlementId: string): Promise<Settlement> {
  const actor = currentUserOrThrow();
  const settlement = findSettlement(settlementId);
  if (settlement.recipient_id !== actor.id && actor.role !== "admin") {
    throw new ApiError("Only the recipient can confirm this settlement.");
  }
  if (settlement.status !== "pending") throw new ApiError("This settlement is no longer pending.");
  settlement.status = "confirmed";
  settlement.updated_at = new Date().toISOString();
  persist();
  return delay(settlement);
}

export async function rejectSettlement(settlementId: string): Promise<Settlement> {
  const actor = currentUserOrThrow();
  const settlement = findSettlement(settlementId);
  if (settlement.recipient_id !== actor.id && actor.role !== "admin") {
    throw new ApiError("Only the recipient can reject this settlement.");
  }
  if (settlement.status !== "pending") throw new ApiError("This settlement is no longer pending.");
  settlement.status = "rejected";
  settlement.updated_at = new Date().toISOString();
  persist();
  return delay(settlement);
}

export async function cancelSettlement(settlementId: string): Promise<Settlement> {
  const actor = currentUserOrThrow();
  const settlement = findSettlement(settlementId);
  if (settlement.payer_id !== actor.id && actor.role !== "admin") {
    throw new ApiError("Only the payer can cancel this settlement.");
  }
  if (settlement.status !== "pending") throw new ApiError("This settlement is no longer pending.");
  settlement.status = "cancelled";
  settlement.updated_at = new Date().toISOString();
  persist();
  return delay(settlement);
}

export async function requestReversal(settlementId: string): Promise<Settlement> {
  const actor = currentUserOrThrow();
  const settlement = findSettlement(settlementId);
  if (settlement.payer_id !== actor.id && settlement.recipient_id !== actor.id && actor.role !== "admin") {
    throw new ApiError("Only a participant in this settlement can request a reversal.");
  }
  if (settlement.status !== "confirmed") throw new ApiError("Only confirmed settlements can be reversed.");
  settlement.status = "reversal_pending";
  settlement.reversal_requested_by = actor.id;
  settlement.updated_at = new Date().toISOString();
  persist();
  return delay(settlement);
}

export async function confirmReversal(settlementId: string): Promise<Settlement> {
  const actor = currentUserOrThrow();
  const settlement = findSettlement(settlementId);
  if (settlement.status !== "reversal_pending")
    throw new ApiError("This settlement has no pending reversal.");
  const isParticipant = settlement.payer_id === actor.id || settlement.recipient_id === actor.id;
  if (!isParticipant && actor.role !== "admin")
    throw new ApiError("Only a participant can confirm this reversal.");
  if (settlement.reversal_requested_by === actor.id) {
    throw new ApiError("Waiting for the other participant to confirm the reversal.");
  }
  settlement.status = "reversed";
  settlement.updated_at = new Date().toISOString();
  persist();
  return delay(settlement);
}

export async function rejectReversal(settlementId: string): Promise<Settlement> {
  const actor = currentUserOrThrow();
  const settlement = findSettlement(settlementId);
  if (settlement.status !== "reversal_pending")
    throw new ApiError("This settlement has no pending reversal.");
  const isParticipant = settlement.payer_id === actor.id || settlement.recipient_id === actor.id;
  if (!isParticipant && actor.role !== "admin")
    throw new ApiError("Only a participant can reject this reversal.");
  settlement.status = "confirmed";
  settlement.reversal_requested_by = undefined;
  settlement.updated_at = new Date().toISOString();
  persist();
  return delay(settlement);
}

// ---------------------------------------------------------------------------
// Refunds
// ---------------------------------------------------------------------------

export async function listRefunds(): Promise<Refund[]> {
  currentUserOrThrow();
  return delay([...db.refunds].sort((a, b) => b.created_at.localeCompare(a.created_at)));
}

export async function getRefund(refundId: string): Promise<Refund> {
  currentUserOrThrow();
  const refund = db.refunds.find((r) => r.id === refundId);
  if (!refund) throw new ApiError("Refund not found.");
  return delay(refund);
}

export async function createRefund(input: {
  group_id: string;
  title: string;
  amount: string;
  participant_ids: string[];
}): Promise<Refund> {
  const actor = currentUserOrThrow();
  const group = assertGroupAccess(input.group_id, actor);
  if (group.status === "archived") throw new ApiError("This group is archived and read-only.");
  if (!input.title.trim()) throw new ApiError("Title is required.");
  if (toCents(input.amount) <= 0) throw new ApiError("Refund amount must be greater than zero.");
  if (input.participant_ids.length === 0) throw new ApiError("Select at least one participant.");
  const nonMember = input.participant_ids.find((id) => !group.member_ids.includes(id));
  if (nonMember) throw new ApiError("Participants must be members of the group.");

  const now = new Date().toISOString();
  const refund: Refund = {
    id: newId("rfd"),
    group_id: input.group_id,
    title: input.title.trim(),
    amount: input.amount,
    participant_ids: input.participant_ids,
    created_by: actor.id,
    status: "pending",
    confirmations: input.participant_ids.map((user_id) => ({
      user_id,
      confirmed: user_id === actor.id,
    })),
    created_at: now,
    updated_at: now,
  };
  db.refunds.push(refund);
  persist();
  return delay(refund);
}

export async function confirmRefund(refundId: string): Promise<Refund> {
  const actor = currentUserOrThrow();
  const refund = db.refunds.find((r) => r.id === refundId);
  if (!refund) throw new ApiError("Refund not found.");
  const confirmation = refund.confirmations.find((c) => c.user_id === actor.id);
  if (!confirmation) throw new ApiError("You are not a participant in this refund.");
  if (refund.status === "confirmed") throw new ApiError("This refund is already confirmed.");
  confirmation.confirmed = true;
  if (refund.confirmations.every((c) => c.confirmed)) {
    refund.status = "confirmed";
  }
  refund.updated_at = new Date().toISOString();
  persist();
  return delay(refund);
}

// ---------------------------------------------------------------------------
// Comments
// ---------------------------------------------------------------------------

function transactionParticipants(type: TransactionType, id: string): string[] {
  if (type === "expense") {
    const e = db.expenses.find((x) => x.id === id);
    if (!e) throw new ApiError("Expense not found.");
    return Array.from(new Set([e.created_by, ...e.participant_ids, ...e.payers.map((p) => p.user_id)]));
  }
  if (type === "settlement") {
    const s = db.settlements.find((x) => x.id === id);
    if (!s) throw new ApiError("Settlement not found.");
    return [s.payer_id, s.recipient_id];
  }
  const r = db.refunds.find((x) => x.id === id);
  if (!r) throw new ApiError("Refund not found.");
  return Array.from(new Set([r.created_by, ...r.participant_ids]));
}

export async function listComments(type: TransactionType, transactionId: string): Promise<Comment[]> {
  currentUserOrThrow();
  return delay(
    db.comments
      .filter((c) => c.transaction_type === type && c.transaction_id === transactionId)
      .sort((a, b) => a.created_at.localeCompare(b.created_at)),
  );
}

export async function createComment(
  type: TransactionType,
  transactionId: string,
  body: string,
): Promise<Comment> {
  const actor = currentUserOrThrow();
  const participants = transactionParticipants(type, transactionId);
  if (actor.role !== "admin" && !participants.includes(actor.id)) {
    throw new ApiError("Only people involved in this transaction can comment.");
  }
  if (!body.trim()) throw new ApiError("Comment can't be empty.");
  const now = new Date().toISOString();
  const comment: Comment = {
    id: newId("cmt"),
    transaction_type: type,
    transaction_id: transactionId,
    author_id: actor.id,
    body: body.trim(),
    created_at: now,
    updated_at: now,
  };
  db.comments.push(comment);
  persist();
  return delay(comment);
}

export async function updateComment(commentId: string, body: string): Promise<Comment> {
  const actor = currentUserOrThrow();
  const comment = db.comments.find((c) => c.id === commentId);
  if (!comment) throw new ApiError("Comment not found.");
  if (comment.author_id !== actor.id) throw new ApiError("You can only edit your own comments.");
  if (!body.trim()) throw new ApiError("Comment can't be empty.");
  comment.body = body.trim();
  comment.updated_at = new Date().toISOString();
  persist();
  return delay(comment);
}

export async function deleteComment(commentId: string): Promise<void> {
  const actor = currentUserOrThrow();
  const comment = db.comments.find((c) => c.id === commentId);
  if (!comment) throw new ApiError("Comment not found.");
  if (comment.author_id !== actor.id) throw new ApiError("You can only delete your own comments.");
  db.comments = db.comments.filter((c) => c.id !== commentId);
  persist();
  return delay(undefined);
}

// ---------------------------------------------------------------------------
// Admin overview
// ---------------------------------------------------------------------------

export interface AdminOverview {
  users_count: number;
  active_users_count: number;
  groups_count: number;
  active_groups_count: number;
  pending_settlements_count: number;
  pending_refunds_count: number;
  expenses_count: number;
}

export async function getAdminOverview(): Promise<AdminOverview> {
  requireAdmin();
  return delay({
    users_count: db.users.length,
    active_users_count: db.users.filter((u) => u.is_active).length,
    groups_count: db.groups.length,
    active_groups_count: db.groups.filter((g) => g.status === "active").length,
    pending_settlements_count: db.settlements.filter(
      (s) => s.status === "pending" || s.status === "reversal_pending",
    ).length,
    pending_refunds_count: db.refunds.filter((r) => r.status === "pending").length,
    expenses_count: db.expenses.length,
  });
}

// ---------------------------------------------------------------------------
// Dev helpers (not part of the real API surface)
// ---------------------------------------------------------------------------

export async function resetDemoData(): Promise<void> {
  clearSession();
  db = buildSeedDb();
  persist();
  return delay(undefined);
}

export async function resetToFreshInstall(): Promise<void> {
  clearSession();
  clearDb();
  db = emptyDb();
  persist();
  return delay(undefined);
}

// Seed on first-ever load so the app is interactive immediately.
if (db.users.length === 0 && localStorage.getItem("balancio_seeded_v1") === null) {
  db = buildSeedDb();
  persist();
  localStorage.setItem("balancio_seeded_v1", "1");
}
