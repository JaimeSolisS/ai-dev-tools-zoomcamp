// Centralized backend client.
//
// Every network call to the Balancio API funnels through this module.
// Nothing else in the app calls `fetch` directly, so the backend base URL,
// auth header, and error handling all live in exactly one place.

import { ApiError } from "./errors";
import type {
  User,
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

// Vite exposes env vars prefixed VITE_ on import.meta.env. Falls back to the
// backend's default `fastapi dev` port for local development.
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000/api/v1";

const TOKEN_KEY = "balancio_token_v1";

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function toQueryString(params: Record<string, unknown>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  const search = new URLSearchParams(entries.map(([k, v]) => [k, String(v)]));
  return `?${search.toString()}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.headers) Object.assign(headers, options.headers as Record<string, string>);
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError("Could not reach the server. Please check your connection and try again.");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let body: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    if (response.status === 401) clearToken();
    const message =
      body && typeof body === "object" && "message" in body
        ? String((body as { message: unknown }).message)
        : "Something went wrong. Please try again.";
    throw new ApiError(message);
  }

  return body as T;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined });
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

interface AuthResponse {
  user: User;
  access_token: string;
  token_type: string;
}

export async function getSetupStatus(): Promise<{ admin_exists: boolean }> {
  return get("/auth/setup-status");
}

export async function setup(input: {
  username: string;
  display_name: string;
  password: string;
}): Promise<{ user: User }> {
  const res = await post<AuthResponse>("/auth/setup", input);
  setToken(res.access_token);
  return { user: res.user };
}

export async function login(username: string, password: string): Promise<{ user: User }> {
  const res = await post<AuthResponse>("/auth/login", { username, password });
  setToken(res.access_token);
  return { user: res.user };
}

export async function logout(): Promise<void> {
  try {
    await post<void>("/auth/logout");
  } finally {
    clearToken();
  }
}

export async function me(): Promise<User | null> {
  if (!getToken()) return null;
  try {
    return await get<User>("/auth/me");
  } catch {
    return null;
  }
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<User> {
  return post<User>("/auth/change-password", { old_password: oldPassword, new_password: newPassword });
}

export async function updateMyTheme(userId: string, theme: Theme): Promise<User> {
  return patch<User>(`/users/${userId}`, { theme });
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export async function listUsers(): Promise<User[]> {
  return get("/users");
}

export async function getUser(userId: string): Promise<User> {
  return get(`/users/${userId}`);
}

export async function createUser(input: {
  username: string;
  display_name: string;
  temporary_password: string;
}): Promise<User> {
  return post<User>("/users", input);
}

export async function updateUser(userId: string, patchBody: { display_name?: string }): Promise<User> {
  return patch<User>(`/users/${userId}`, patchBody);
}

export async function resetPassword(userId: string, newTemporaryPassword: string): Promise<void> {
  return post<void>(`/users/${userId}/reset-password`, { new_temporary_password: newTemporaryPassword });
}

export async function forcePasswordChange(userId: string): Promise<void> {
  return post<void>(`/users/${userId}/force-password-change`);
}

export async function deactivateUser(userId: string): Promise<User> {
  return post<User>(`/users/${userId}/deactivate`);
}

export async function activateUser(userId: string): Promise<User> {
  return post<User>(`/users/${userId}/activate`);
}

// ---------------------------------------------------------------------------
// Groups
// ---------------------------------------------------------------------------

export async function listGroups(): Promise<Group[]> {
  return get("/groups");
}

export async function getGroup(groupId: string): Promise<Group> {
  return get(`/groups/${groupId}`);
}

export async function createGroup(input: {
  name: string;
  description?: string;
  member_ids: string[];
}): Promise<Group> {
  return post<Group>("/groups", input);
}

export async function updateGroup(
  groupId: string,
  patchBody: { name?: string; description?: string },
): Promise<Group> {
  return patch<Group>(`/groups/${groupId}`, patchBody);
}

export async function addGroupMember(groupId: string, userId: string): Promise<Group> {
  return post<Group>(`/groups/${groupId}/members`, { user_id: userId });
}

export async function removeGroupMember(groupId: string, userId: string): Promise<Group> {
  return del<Group>(`/groups/${groupId}/members/${userId}`);
}

export async function leaveGroup(groupId: string): Promise<Group> {
  return post<Group>(`/groups/${groupId}/leave`);
}

export async function archiveGroup(groupId: string): Promise<Group> {
  return post<Group>(`/groups/${groupId}/archive`);
}

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

export async function listCategories(groupId?: string): Promise<Category[]> {
  return get(`/categories${toQueryString({ group_id: groupId })}`);
}

export async function createCategory(input: { name: string; group_id: string | null }): Promise<Category> {
  return post<Category>("/categories", input);
}

export async function updateCategory(categoryId: string, patchBody: { name: string }): Promise<Category> {
  return patch<Category>(`/categories/${categoryId}`, patchBody);
}

export async function deleteCategory(categoryId: string): Promise<void> {
  return del<void>(`/categories/${categoryId}`);
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

export async function listExpenses(filters: ExpenseFilters = {}): Promise<Page<Expense>> {
  return get(`/expenses${toQueryString({ ...filters })}`);
}

export async function getExpense(expenseId: string): Promise<Expense> {
  return get(`/expenses/${expenseId}`);
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
  return post<Expense>("/expenses", input);
}

export async function updateExpense(expenseId: string, patchBody: Partial<ExpenseInput>): Promise<Expense> {
  return patch<Expense>(`/expenses/${expenseId}`, patchBody);
}

export async function deleteExpense(expenseId: string): Promise<void> {
  return del<void>(`/expenses/${expenseId}`);
}

export async function duplicateExpense(expenseId: string): Promise<ExpenseInput> {
  return post<ExpenseInput>(`/expenses/${expenseId}/duplicate`);
}

// ---------------------------------------------------------------------------
// Balances
// ---------------------------------------------------------------------------

export async function getGroupBalances(groupId: string): Promise<GroupBalances> {
  return get(`/groups/${groupId}/balances`);
}

export async function getGlobalBalances(): Promise<GlobalBalances> {
  return get("/balances/global");
}

export async function getMyBalances(): Promise<GlobalBalances> {
  return get("/balances/me");
}

export async function getSettlementSuggestions(): Promise<PairBalance[]> {
  return get("/settlement-suggestions");
}

// ---------------------------------------------------------------------------
// Settlements
// ---------------------------------------------------------------------------

export async function listSettlements(): Promise<Settlement[]> {
  return get("/settlements");
}

export async function createSettlement(input: {
  payer_id: string;
  recipient_id: string;
  amount: string;
  note?: string;
}): Promise<Settlement> {
  return post<Settlement>("/settlements", input);
}

export async function updateSettlement(
  settlementId: string,
  patchBody: { amount?: string; note?: string },
): Promise<Settlement> {
  return patch<Settlement>(`/settlements/${settlementId}`, patchBody);
}

export async function confirmSettlement(settlementId: string): Promise<Settlement> {
  return post<Settlement>(`/settlements/${settlementId}/confirm`);
}

export async function rejectSettlement(settlementId: string): Promise<Settlement> {
  return post<Settlement>(`/settlements/${settlementId}/reject`);
}

export async function cancelSettlement(settlementId: string): Promise<Settlement> {
  return post<Settlement>(`/settlements/${settlementId}/cancel`);
}

export async function requestReversal(settlementId: string): Promise<Settlement> {
  return post<Settlement>(`/settlements/${settlementId}/request-reversal`);
}

export async function confirmReversal(settlementId: string): Promise<Settlement> {
  return post<Settlement>(`/settlements/${settlementId}/confirm-reversal`);
}

export async function rejectReversal(settlementId: string): Promise<Settlement> {
  return post<Settlement>(`/settlements/${settlementId}/reject-reversal`);
}

// ---------------------------------------------------------------------------
// Refunds
// ---------------------------------------------------------------------------

export async function listRefunds(): Promise<Refund[]> {
  return get("/refunds");
}

export async function getRefund(refundId: string): Promise<Refund> {
  return get(`/refunds/${refundId}`);
}

export async function createRefund(input: {
  group_id: string;
  title: string;
  amount: string;
  participant_ids: string[];
}): Promise<Refund> {
  return post<Refund>("/refunds", input);
}

export async function confirmRefund(refundId: string): Promise<Refund> {
  return post<Refund>(`/refunds/${refundId}/confirm`);
}

// ---------------------------------------------------------------------------
// Comments
// ---------------------------------------------------------------------------

export async function listComments(type: TransactionType, transactionId: string): Promise<Comment[]> {
  return get(`/${type}/${transactionId}/comments`);
}

export async function createComment(
  type: TransactionType,
  transactionId: string,
  body: string,
): Promise<Comment> {
  return post<Comment>(`/${type}/${transactionId}/comments`, { body });
}

export async function updateComment(commentId: string, body: string): Promise<Comment> {
  return patch<Comment>(`/comments/${commentId}`, { body });
}

export async function deleteComment(commentId: string): Promise<void> {
  return del<void>(`/comments/${commentId}`);
}

// ---------------------------------------------------------------------------
// Admin
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
  return get("/admin/overview");
}
