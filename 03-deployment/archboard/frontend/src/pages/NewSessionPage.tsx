import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { AppHeader } from '../components/AppHeader';
import { ErrorText } from '../components/ui';
import { errorMessage, type SessionSummary } from '../services';
import { useBackend } from '../services/ServiceProvider';

export function NewSessionPage() {
  const backend = useBackend();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [duration, setDuration] = useState('45');
  const [scheduledAt, setScheduledAt] = useState('');
  const [template, setTemplate] = useState('');
  const [templates, setTemplates] = useState<SessionSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    backend.sessions
      .list()
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, [backend]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const session = await backend.sessions.create({
        title,
        prompt,
        durationMinutes: duration ? Number(duration) : null,
        scheduledAt: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        templateSessionId: template || null,
      });
      navigate(`/sessions/${session.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  };

  const onTemplate = (id: string) => {
    setTemplate(id);
    const t = templates.find((s) => s.id === id);
    if (t) {
      if (!title) setTitle(t.title.replace(/^Example: /, ''));
      if (!prompt) setPrompt(t.prompt);
    }
  };

  return (
    <div className="page">
      <AppHeader />
      <main className="container narrow-container">
        <Link to="/" className="back-link">
          <ArrowLeft size={16} aria-hidden /> All interviews
        </Link>
        <h1>New interview</h1>
        <form className="card stack" onSubmit={submit}>
          <label className="field">
            <span>Title</span>
            <input required maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Design a ride-sharing service" autoFocus />
          </label>
          <label className="field">
            <span>
              Problem statement <span className="muted">(optional, shown to participants)</span>
            </span>
            <textarea rows={6} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe requirements, scale, and constraints…" />
          </label>
          <div className="field-row">
            <label className="field">
              <span>Duration</span>
              <select value={duration} onChange={(e) => setDuration(e.target.value)}>
                <option value="">No timer</option>
                <option value="30">30 minutes</option>
                <option value="45">45 minutes</option>
                <option value="60">60 minutes</option>
                <option value="90">90 minutes</option>
              </select>
            </label>
            <label className="field">
              <span>
                Scheduled for <span className="muted">(optional)</span>
              </span>
              <input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
            </label>
          </div>
          <label className="field">
            <span>Start from</span>
            <select value={template} onChange={(e) => onTemplate(e.target.value)}>
              <option value="">Blank canvas</option>
              {templates
                .filter((t) => t.state !== 'archived')
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    Copy of “{t.title}”
                  </option>
                ))}
            </select>
          </label>
          <ErrorText>{error}</ErrorText>
          <div className="form-actions">
            <Link to="/" className="button">
              Cancel
            </Link>
            <button className="button primary" disabled={busy}>
              {busy ? 'Creating…' : 'Create interview'}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
