export type Role = "admin" | "user";
export type Theme = "light" | "dark";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  theme: Theme;
  created_at: string;
  updated_at: string;
}

export type GroupStatus = "active" | "archived";

export interface Group {
  id: string;
  name: string;
  description?: string;
  member_ids: string[];
  status: GroupStatus;
  created_at: string;
  updated_at: string;
}

export interface Category {
  id: string;
  name: string;
  group_id: string | null; // null = global category
  created_at: string;
}

export interface Payer {
  user_id: string;
  amount: string;
}

export interface Share {
  user_id: string;
  amount: string;
}

export interface Expense {
  id: string;
  group_id: string;
  title: string;
  amount: string;
  expense_date: string;
  category_id: string | null;
  note?: string;
  tags: string[];
  created_by: string;
  payers: Payer[];
  participant_ids: string[];
  shares: Share[];
  created_at: string;
  updated_at: string;
}

export type SettlementStatus =
  "pending" | "confirmed" | "rejected" | "cancelled" | "reversal_pending" | "reversed";

export interface Settlement {
  id: string;
  payer_id: string;
  recipient_id: string;
  amount: string;
  note?: string;
  status: SettlementStatus;
  reversal_requested_by?: string;
  created_at: string;
  updated_at: string;
}

export type RefundStatus = "pending" | "confirmed";

export interface RefundConfirmation {
  user_id: string;
  confirmed: boolean;
}

export interface Refund {
  id: string;
  group_id: string;
  title: string;
  amount: string;
  participant_ids: string[];
  created_by: string;
  status: RefundStatus;
  confirmations: RefundConfirmation[];
  created_at: string;
  updated_at: string;
}

export type TransactionType = "expense" | "settlement" | "refund";

export interface Comment {
  id: string;
  transaction_type: TransactionType;
  transaction_id: string;
  author_id: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface PairBalance {
  from_user_id: string; // owes
  to_user_id: string; // is owed
  amount: string;
}

export interface GroupBalances {
  group_id: string;
  net: Record<string, string>;
  pairs: PairBalance[];
}

export interface GlobalBalances {
  current: {
    net: Record<string, string>;
    pairs: PairBalance[];
  };
  confirmed: {
    net: Record<string, string>;
    pairs: PairBalance[];
  };
  contributions: Record<string, string[]>; // pair key -> group ids contributing
}

export interface ApiError {
  message: string;
}
