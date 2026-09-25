# Archboard: System Design Interview Frontend

A React + TypeScript frontend for live system-design interviews, built from
[`../_docs/spec.md`](../_docs/spec.md). An interviewer creates a session and shares a link.
Candidates join and draw on a shared real-time canvas. The finished canvas is saved for review.

The app runs with **no backend**. Every backend call goes through a single services layer,
and a mock implementation of that layer runs entirely in the browser.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # unit, integration and UI tests (Vitest + Testing Library)
npm run build      # type-check and production build
```

### Try a live interview

1. Sign in with any email. The mock shows an **Open sign-in link** button instead of sending an email.
2. Open the example session or create a new one. Click **Share**, then **Create candidate link**.
3. Paste the link into **another tab** and join as the candidate. Each tab is its own participant,
   and tabs sync through `BroadcastChannel`. Cursors, selections, edits, locking and ending all
   propagate between tabs.
4. To test reconnects, use DevTools → Network → *Offline*. Edits you make while offline are
   queued and sync when the connection comes back.

## Architecture

```
src/
  services/                  ← the only place that talks to a "backend"
    api.ts                   BackendService interface (auth, sessions, join, canvas, realtime),
                             each method annotated with the REST/WS endpoint it maps to
    types.ts                 request/response + WebSocket message contract
    permissions.ts           permission matrix (spec §9), shared by UI and backends
    errors.ts                ApiError with stable error codes
    mock/                    in-browser implementation of BackendService
      mockBackend.ts         authorization, guest links, joins, persistence, realtime fan-out
      db.ts, storage.ts      "tables" in localStorage (or in-memory for tests)
      bus.ts                 BroadcastChannel / in-process message bus
      seed.ts                example session for new users
    http/httpBackend.ts      placeholder for the real REST + WebSocket client
    index.ts                 createBackend(): picks mock or http from VITE_BACKEND
    ServiceProvider.tsx      React context → useBackend()
  canvas/                    pure, framework-free canvas logic
    model.ts                 LWW element-map CRDT, Lamport clock, undo/redo, clipboard
    geometry.ts              connectors, hit-testing, alignment guides, viewport math
    editing.ts               create/move/resize/group/reorder operations
    catalog.ts               component palette (spec §6.4)
  hooks/useRoom.ts           optimistic editing, op queue, resync, presence, scoped undo
  components/, pages/        UI
```

Components never call `fetch` or open sockets themselves. They call `useBackend()`. To plug in
the real backend, implement `BackendService` in `services/http/` and set `VITE_BACKEND=http`
(see `.env.example`). Nothing else changes.

### How the mock behaves like a real backend

- Every call waits `VITE_MOCK_LATENCY_MS` (default 120 ms) and returns cloned data.
- It authorizes every request and every socket message. Candidates can't read other sessions,
  and non-owners get `NOT_FOUND`.
- Guest tokens carry 192 bits of entropy. Only their SHA-256 hash is stored. Links can be
  revoked, rotated, and limited by expiry or number of uses. A session holds at most 10
  participants.
- Canvas operations are validated and de-duplicated by operation id, then persisted and fanned
  out to other connections. Operations from candidates are rejected while editing is locked.
- A final snapshot is saved when a session ends, and another before the canvas is cleared.
  Both can be restored.
- Session creation, link changes, permission changes, removals and session end are written to
  an audit log.

### Collaboration model

The canvas document is a last-writer-wins map of elements. Each element carries a Lamport
stamp, and deleted elements are kept as tombstones. Applying operations is commutative and
idempotent, so out-of-order and duplicate messages still converge, and edits to different
objects never overwrite each other. Local edits apply optimistically and stay pending until the
server acknowledges them. After a reconnect or a rejected edit, the client reloads the
authoritative snapshot and re-applies its unacknowledged operations.

## Spec coverage (MVP)

Implemented:

- **Accounts and sessions:** magic-link sign-in; dashboard with open, copy link, duplicate and
  archive; session lifecycle (draft → live → ended → reopen, and archive).
- **Joining:** guest links for candidate, interviewer and observer roles; a lobby with a name
  field, privacy notice and browser warning.
- **Canvas basics:** infinite pan and zoom; the full component palette; text and sticky notes;
  straight, elbow and curved connectors with labels, arrowheads, dash, colour and width; drag to
  redirect a connector end.
- **Drawing:** pen, highlighter, and a stroke eraser.
- **Editing:** multi-select with a marquee or shift-click; move and resize; snap to grid and
  alignment guides; group and ungroup; layer order; copy, cut, paste and duplicate; per-user
  undo and redo.
- **Collaboration:** remote cursors and selections labelled with names; connection status;
  autosave; offline queue.
- **Host controls:** lock candidate editing, remove a participant, hide cursors, clear the
  canvas and restore snapshots, visible timer, export to JSON.
- **Keyboard access:** Tab through canvas objects; move them with the arrow keys; Enter to
  relabel; connect via "Connect to…" in the properties panel.

Not done yet: organisation SSO, PNG/PDF export, the optional laser pointer, and the real
backend.
