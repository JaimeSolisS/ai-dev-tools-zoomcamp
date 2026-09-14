import { useEffect, useState } from "react";
import type { Comment, TransactionType, User } from "../types";
import * as api from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button, Textarea, ErrorText, Spinner } from "./ui";

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export function CommentThread({
  transactionType,
  transactionId,
  users,
  allowed,
}: {
  transactionType: TransactionType;
  transactionId: string;
  users: User[];
  allowed: boolean;
}) {
  const { user: me } = useAuth();
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function userName(id: string) {
    return users.find((u) => u.id === id)?.display_name ?? "Unknown";
  }

  async function load() {
    const list = await api.listComments(transactionType, transactionId);
    setComments(list);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transactionType, transactionId]);

  async function submit() {
    if (!draft.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createComment(transactionType, transactionId, draft);
      setDraft("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not post comment.");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(id: string) {
    setBusy(true);
    setError(null);
    try {
      await api.updateComment(id, editDraft);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update comment.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await api.deleteComment(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete comment.");
    } finally {
      setBusy(false);
    }
  }

  if (comments === null) {
    return <Spinner />;
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Comments</h3>
      {comments.length === 0 && <p className="text-sm text-slate-400">No comments yet.</p>}
      <ul className="space-y-2">
        {comments.map((c) => (
          <li key={c.id} className="rounded-lg bg-slate-50 p-2.5 text-sm dark:bg-slate-700/50">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-slate-700 dark:text-slate-200">{userName(c.author_id)}</span>
              <span className="text-xs text-slate-400">{timeAgo(c.created_at)}</span>
            </div>
            {editingId === c.id ? (
              <div className="mt-1 space-y-2">
                <Textarea value={editDraft} onChange={(e) => setEditDraft(e.target.value)} rows={2} />
                <div className="flex gap-2">
                  <Button onClick={() => saveEdit(c.id)} disabled={busy}>
                    Save
                  </Button>
                  <Button variant="secondary" onClick={() => setEditingId(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <p className="mt-1 whitespace-pre-wrap text-slate-600 dark:text-slate-300">{c.body}</p>
            )}
            {me?.id === c.author_id && editingId !== c.id && (
              <div className="mt-1 flex gap-3 text-xs">
                <button
                  className="text-slate-500 hover:underline"
                  onClick={() => {
                    setEditingId(c.id);
                    setEditDraft(c.body);
                  }}
                >
                  Edit
                </button>
                <button className="text-rose-500 hover:underline" onClick={() => remove(c.id)}>
                  Delete
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {allowed ? (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a comment…"
            rows={2}
          />
          <ErrorText message={error} />
          <Button onClick={submit} disabled={busy || !draft.trim()}>
            Post comment
          </Button>
        </div>
      ) : (
        <p className="text-xs text-slate-400">Only people involved in this transaction can comment.</p>
      )}
    </div>
  );
}
