import { useEffect, useState } from 'react';
import {
  ArrowLeftRight,
  BringToFront,
  ChevronsDown,
  ChevronsUp,
  CopyPlus,
  Group,
  PanelRightClose,
  SendToBack,
  Trash2,
  Ungroup,
} from 'lucide-react';
import { getComponent, INK_COLORS, STICKY_COLORS } from '../../canvas/catalog';
import type { LayerMove } from '../../canvas/editing';
import type { CanvasElement, ConnectorElement, Routing, ShapeElement, StrokeElement } from '../../canvas/types';
import type { InterviewSession, Permissions } from '../../services';
import { IconButton } from '../ui';

export interface PanelActions {
  update(element: CanvasElement): void;
  beginEdit(): void;
  endEdit(): void;
  remove(): void;
  duplicate(): void;
  group(): void;
  ungroup(): void;
  reorder(move: LayerMove): void;
  connectTo(targetId: string): void;
}

interface Props {
  selected: CanvasElement[];
  elements: CanvasElement[];
  canEdit: boolean;
  session: InterviewSession;
  permissions: Permissions;
  actions: PanelActions;
  onSavePrompt(prompt: string): Promise<void>;
  onCollapse(): void;
}

export function PropertiesPanel(props: Props) {
  const { selected, onCollapse } = props;
  return (
    <aside className="side-panel" aria-label={selected.length ? 'Properties' : 'Interview prompt'}>
      <header className="side-panel-header">
        <h2>{selected.length === 0 ? 'Interview prompt' : selected.length === 1 ? 'Properties' : `${selected.length} selected`}</h2>
        <IconButton label="Collapse panel" onClick={onCollapse} className="tooltip-left">
          <PanelRightClose size={17} />
        </IconButton>
      </header>
      <div className="side-panel-body">{selected.length === 0 ? <PromptView {...props} /> : <SelectionView {...props} />}</div>
    </aside>
  );
}

function PromptView({ session, permissions, onSavePrompt }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.prompt);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!editing) setDraft(session.prompt);
  }, [session.prompt, editing]);

  return (
    <div className="stack">
      <h3 className="prompt-title">{session.title}</h3>
      {editing ? (
        <>
          <textarea className="prompt-editor" rows={10} value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Problem statement" autoFocus />
          <div className="form-actions">
            <button type="button" className="button small" onClick={() => setEditing(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="button small primary"
              disabled={saving}
              onClick={async () => {
                setSaving(true);
                try {
                  await onSavePrompt(draft);
                  setEditing(false);
                } finally {
                  setSaving(false);
                }
              }}
            >
              Save
            </button>
          </div>
        </>
      ) : (
        <>
          {session.prompt ? <p className="prompt-text">{session.prompt}</p> : <p className="muted">No problem statement was provided.</p>}
          {permissions.canEditSettings && (
            <button type="button" className="button small" onClick={() => setEditing(true)}>
              Edit prompt
            </button>
          )}
        </>
      )}
      <details className="shortcuts">
        <summary>Keyboard shortcuts</summary>
        <dl>
          <dt>V / H / P / I / E / T / S / C</dt>
          <dd>Select, pan, pen, highlighter, eraser, text, sticky, connector</dd>
          <dt>L</dt>
          <dd>Component library</dd>
          <dt>Tab</dt>
          <dd>Move focus between canvas objects</dd>
          <dt>Arrows (Shift = ×10)</dt>
          <dd>Move selection</dd>
          <dt>Enter</dt>
          <dd>Edit label</dd>
          <dt>Delete</dt>
          <dd>Delete selection</dd>
          <dt>⌘/Ctrl Z, ⇧⌘Z</dt>
          <dd>Undo, redo (your own changes)</dd>
          <dt>⌘/Ctrl C, X, V, D</dt>
          <dd>Copy, cut, paste, duplicate</dd>
          <dt>⌘/Ctrl G, ⇧⌘G</dt>
          <dd>Group, ungroup</dd>
          <dt>] / [ (⌘ = to front/back)</dt>
          <dd>Layer order</dd>
          <dt>Space + drag, scroll</dt>
          <dd>Pan</dd>
          <dt>⌘/Ctrl scroll, + / −</dt>
          <dd>Zoom</dd>
          <dt>⇧1 / ⇧0</dt>
          <dd>Zoom to fit, reset view</dd>
        </dl>
      </details>
    </div>
  );
}

function SelectionView({ selected, elements, canEdit, actions }: Props) {
  const single = selected.length === 1 ? selected[0] : null;
  const grouped = selected.some((e) => e.groupId);
  return (
    <div className="stack">
      {single?.kind === 'shape' && <ShapeFields el={single} elements={elements} canEdit={canEdit} actions={actions} />}
      {single?.kind === 'connector' && <ConnectorFields el={single} canEdit={canEdit} actions={actions} />}
      {single?.kind === 'stroke' && <StrokeFields el={single} canEdit={canEdit} actions={actions} />}
      {!single && <p className="muted">{describeMulti(selected)}</p>}

      {canEdit && (
        <>
          <div className="panel-section">
            <h3>Arrange</h3>
            <div className="button-row">
              <IconButton label="Bring to front" shortcut="⌘]" onClick={() => actions.reorder('front')}>
                <BringToFront size={17} />
              </IconButton>
              <IconButton label="Bring forward" shortcut="]" onClick={() => actions.reorder('forward')}>
                <ChevronsUp size={17} />
              </IconButton>
              <IconButton label="Send backward" shortcut="[" onClick={() => actions.reorder('backward')}>
                <ChevronsDown size={17} />
              </IconButton>
              <IconButton label="Send to back" shortcut="⌘[" onClick={() => actions.reorder('back')}>
                <SendToBack size={17} />
              </IconButton>
              {selected.length > 1 && (
                <IconButton label="Group" shortcut="⌘G" onClick={actions.group}>
                  <Group size={17} />
                </IconButton>
              )}
              {grouped && (
                <IconButton label="Ungroup" shortcut="⇧⌘G" onClick={actions.ungroup}>
                  <Ungroup size={17} />
                </IconButton>
              )}
            </div>
          </div>
          <div className="panel-section danger-zone">
            <button type="button" className="button small" onClick={actions.duplicate}>
              <CopyPlus size={15} aria-hidden /> Duplicate
            </button>
            <button type="button" className="button small ghost-danger" onClick={actions.remove}>
              <Trash2 size={15} aria-hidden /> Delete
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function describeMulti(selected: CanvasElement[]): string {
  const counts = { shape: 0, connector: 0, stroke: 0 };
  for (const el of selected) counts[el.kind]++;
  return [
    counts.shape && `${counts.shape} component${counts.shape > 1 ? 's' : ''}`,
    counts.connector && `${counts.connector} connector${counts.connector > 1 ? 's' : ''}`,
    counts.stroke && `${counts.stroke} drawing${counts.stroke > 1 ? 's' : ''}`,
  ]
    .filter(Boolean)
    .join(', ');
}

/** Text input that commits on every change as one undoable edit. */
function LiveText({
  label,
  value,
  onChange,
  disabled,
  multiline,
  actions,
  placeholder,
}: {
  label: string;
  value: string;
  onChange(v: string): void;
  disabled: boolean;
  multiline?: boolean;
  actions: PanelActions;
  placeholder?: string;
}) {
  const common = {
    value,
    disabled,
    placeholder,
    maxLength: 2000,
    onFocus: actions.beginEdit,
    onBlur: actions.endEdit,
    onKeyDown: (e: React.KeyboardEvent) => e.stopPropagation(),
  };
  return (
    <label className="field">
      <span>{label}</span>
      {multiline ? (
        <textarea rows={3} {...common} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input {...common} onChange={(e) => onChange(e.target.value)} />
      )}
    </label>
  );
}

function ShapeFields({ el, elements, canEdit, actions }: { el: ShapeElement; elements: CanvasElement[]; canEdit: boolean; actions: PanelActions }) {
  const def = getComponent(el.componentType);
  const [target, setTarget] = useState('');
  const others = elements.filter((e): e is ShapeElement => e.kind === 'shape' && e.id !== el.id);
  const numeric = (key: 'w' | 'h', v: string) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return;
    const min = key === 'w' ? def.minWidth : def.minHeight;
    actions.update({ ...el, [key]: Math.max(min, Math.round(n)) });
  };
  return (
    <>
      <p className="element-type">{def.name}</p>
      <LiveText label={def.shape === 'sticky' || def.shape === 'text' ? 'Text' : 'Label'} value={el.label} multiline={def.shape === 'sticky' || def.shape === 'text'} disabled={!canEdit} actions={actions} onChange={(label) => actions.update({ ...el, label })} />
      {def.shape !== 'sticky' && def.shape !== 'text' && (
        <LiveText label="Description" value={el.description ?? ''} multiline disabled={!canEdit} actions={actions} placeholder="Optional notes" onChange={(description) => actions.update({ ...el, description })} />
      )}
      {def.shape === 'sticky' && canEdit && (
        <div className="field">
          <span>Colour</span>
          <div className="swatches">
            {STICKY_COLORS.map((c) => (
              <button key={c} type="button" className={`swatch${(el.fill ?? def.fill) === c ? ' selected' : ''}`} style={{ background: c }} aria-label={`Note colour ${c}`} aria-pressed={(el.fill ?? def.fill) === c} onClick={() => actions.update({ ...el, fill: c })} />
            ))}
          </div>
        </div>
      )}
      <div className="field-row">
        <label className="field">
          <span>Width</span>
          <input type="number" min={def.minWidth} value={Math.round(el.w)} disabled={!canEdit} onChange={(e) => numeric('w', e.target.value)} onKeyDown={(e) => e.stopPropagation()} />
        </label>
        <label className="field">
          <span>Height</span>
          <input type="number" min={def.minHeight} value={Math.round(el.h)} disabled={!canEdit} onChange={(e) => numeric('h', e.target.value)} onKeyDown={(e) => e.stopPropagation()} />
        </label>
      </div>
      {canEdit && others.length > 0 && (
        <div className="field">
          <span>Connect to</span>
          <div className="inline-form">
            <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Connect to component">
              <option value="">Choose a component…</option>
              {others.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label || getComponent(o.componentType).name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="button small"
              disabled={!target}
              onClick={() => {
                actions.connectTo(target);
                setTarget('');
              }}
            >
              Connect
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function ConnectorFields({ el, canEdit, actions }: { el: ConnectorElement; canEdit: boolean; actions: PanelActions }) {
  const set = (patch: Partial<ConnectorElement>) => actions.update({ ...el, ...patch });
  return (
    <>
      <p className="element-type">Connector</p>
      <LiveText label="Label" value={el.label} disabled={!canEdit} actions={actions} placeholder="e.g. HTTPS, events" onChange={(label) => set({ label })} />
      <div className="field">
        <span>Style</span>
        <div className="segmented" role="radiogroup" aria-label="Routing">
          {(['straight', 'elbow', 'curved'] as Routing[]).map((r) => (
            <button key={r} type="button" role="radio" aria-checked={el.routing === r} disabled={!canEdit} className={el.routing === r ? 'active' : ''} onClick={() => set({ routing: r })}>
              {r}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <span>Arrowheads</span>
        <div className="checkbox-group">
          <label className="checkbox-row">
            <input type="checkbox" checked={el.arrowStart} disabled={!canEdit} onChange={(e) => set({ arrowStart: e.target.checked })} /> Start
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={el.arrowEnd} disabled={!canEdit} onChange={(e) => set({ arrowEnd: e.target.checked })} /> End
          </label>
          <label className="checkbox-row">
            <input type="checkbox" checked={el.dashed} disabled={!canEdit} onChange={(e) => set({ dashed: e.target.checked })} /> Dashed
          </label>
        </div>
      </div>
      <div className="field">
        <span>Line width</span>
        <div className="segmented" role="radiogroup" aria-label="Line width">
          {([1, 2, 3] as const).map((w) => (
            <button key={w} type="button" role="radio" aria-checked={el.width === w} disabled={!canEdit} className={el.width === w ? 'active' : ''} onClick={() => set({ width: w })}>
              {['Thin', 'Medium', 'Thick'][w - 1]}
            </button>
          ))}
        </div>
      </div>
      <ColorField value={el.color} disabled={!canEdit} onChange={(color) => set({ color })} />
      {canEdit && (
        <button type="button" className="button small" onClick={() => set({ from: el.to, to: el.from })}>
          <ArrowLeftRight size={15} aria-hidden /> Reverse direction
        </button>
      )}
    </>
  );
}

function StrokeFields({ el, canEdit, actions }: { el: StrokeElement; canEdit: boolean; actions: PanelActions }) {
  return (
    <>
      <p className="element-type">{el.tool === 'highlighter' ? 'Highlighter stroke' : 'Pen stroke'}</p>
      <ColorField value={el.color} disabled={!canEdit} onChange={(color) => actions.update({ ...el, color })} />
    </>
  );
}

function ColorField({ value, disabled, onChange }: { value: string; disabled: boolean; onChange(c: string): void }) {
  const colors = [...INK_COLORS, '#334155'];
  return (
    <div className="field">
      <span>Colour</span>
      <div className="swatches">
        {colors.map((c) => (
          <button key={c} type="button" disabled={disabled} className={`swatch${value === c ? ' selected' : ''}`} style={{ background: c }} aria-label={`Colour ${c}`} aria-pressed={value === c} onClick={() => onChange(c)} />
        ))}
      </div>
    </div>
  );
}
