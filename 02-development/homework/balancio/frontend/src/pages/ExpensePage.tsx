import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import * as api from "../api/client";
import type { Category, Expense, Group } from "../types";
import { useAuth } from "../auth/AuthContext";
import { useUsers } from "../contexts/UsersContext";
import { Badge, Button, Card, ErrorText, PageHeader, Spinner } from "../components/ui";
import { Money } from "../components/Money";
import { CommentThread } from "../components/CommentThread";
import { ConfirmDialog } from "../components/ConfirmDialog";

export function ExpensePage() {
  const { expenseId } = useParams<{ expenseId: string }>();
  const { user } = useAuth();
  const { users, nameOf } = useUsers();
  const navigate = useNavigate();

  const [expense, setExpense] = useState<Expense | null>(null);
  const [group, setGroup] = useState<Group | null>(null);
  const [category, setCategory] = useState<Category | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);

  async function load() {
    if (!expenseId) return;
    const e = await api.getExpense(expenseId);
    setExpense(e);
    const g = await api.getGroup(e.group_id);
    setGroup(g);
    if (e.category_id) {
      const cats = await api.listCategories(e.group_id);
      setCategory(cats.find((c) => c.id === e.category_id) ?? null);
    } else {
      setCategory(null);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expenseId]);

  async function handleDuplicate() {
    if (!expense) return;
    const draft = await api.duplicateExpense(expense.id);
    navigate(`/groups/${expense.group_id}/expenses/new`, { state: { draft } });
  }

  if (!expense || !group) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  const canEdit = user?.role === "admin" || user?.id === expense.created_by;
  const involved =
    !!user &&
    (expense.created_by === user.id ||
      expense.participant_ids.includes(user.id) ||
      expense.payers.some((p) => p.user_id === user.id));

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        title={expense.title}
        subtitle={`${group.name} · ${expense.expense_date}`}
        actions={
          group.status === "active" &&
          canEdit && (
            <>
              <Button variant="secondary" onClick={handleDuplicate}>
                Duplicate
              </Button>
              <Button variant="secondary" onClick={() => navigate(`/expenses/${expense.id}/edit`)}>
                Edit
              </Button>
              <Button variant="danger" onClick={() => setShowDelete(true)}>
                Delete
              </Button>
            </>
          )
        }
      />

      <ErrorText message={error} />

      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-3xl font-bold text-slate-900 dark:text-white">
            <Money amount={expense.amount} />
          </span>
          {category && <Badge tone="info">{category.name}</Badge>}
        </div>

        {expense.note && <p className="text-sm text-slate-600 dark:text-slate-300">{expense.note}</p>}

        {expense.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {expense.tags.map((t) => (
              <Badge key={t}>#{t}</Badge>
            ))}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase text-slate-400">Paid by</h3>
            <ul className="space-y-1 text-sm">
              {expense.payers.map((p) => (
                <li key={p.user_id} className="flex justify-between">
                  <span>{nameOf(p.user_id)}</span>
                  <Money amount={p.amount} />
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase text-slate-400">Split between</h3>
            <ul className="space-y-1 text-sm">
              {expense.shares.map((s) => (
                <li key={s.user_id} className="flex justify-between">
                  <span>{nameOf(s.user_id)}</span>
                  <Money amount={s.amount} />
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="text-xs text-slate-400">Added by {nameOf(expense.created_by)}</p>
      </Card>

      <Card>
        <CommentThread
          transactionType="expense"
          transactionId={expense.id}
          users={users}
          allowed={involved}
        />
      </Card>

      {showDelete && (
        <ConfirmDialog
          title="Delete expense"
          description="This action is permanent. Balances will be recalculated after deletion."
          danger
          confirmLabel="Delete"
          onConfirm={async () => {
            try {
              await api.deleteExpense(expense.id);
              navigate(`/groups/${expense.group_id}`);
            } catch (err) {
              setError(err instanceof Error ? err.message : "Could not delete expense.");
              throw err;
            }
          }}
          onClose={() => setShowDelete(false)}
        />
      )}
    </div>
  );
}
