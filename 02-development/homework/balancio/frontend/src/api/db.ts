import type { User, Group, Category, Expense, Settlement, Refund, Comment } from "../types";

export interface Db {
  users: User[];
  groups: Group[];
  categories: Category[];
  expenses: Expense[];
  settlements: Settlement[];
  refunds: Refund[];
  comments: Comment[];
  // password_hash is kept separately (mock: plain text) so `User` objects
  // handed to the UI never carry credentials.
  passwords: Record<string, string>;
}

const STORAGE_KEY = "balancio_db_v1";

export function emptyDb(): Db {
  return {
    users: [],
    groups: [],
    categories: [],
    expenses: [],
    settlements: [],
    refunds: [],
    comments: [],
    passwords: {},
  };
}

export function loadDb(): Db | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Db;
  } catch {
    return null;
  }
}

export function saveDb(db: Db) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(db));
}

export function clearDb() {
  localStorage.removeItem(STORAGE_KEY);
}
