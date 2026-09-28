import { Eraser, Hand, Highlighter, LayoutGrid, MousePointer2, Pen, Spline, StickyNote, Type } from 'lucide-react';
import type { ReactNode } from 'react';
import { HIGHLIGHT_COLORS, INK_COLORS } from '../../canvas/catalog';
import type { Routing } from '../../canvas/types';
import type { Tool, ToolOptions } from '../canvas/CanvasView';
import { IconButton } from '../ui';

const TOOLS: { tool: Tool; label: string; key: string; icon: ReactNode; edit: boolean }[] = [
  { tool: 'select', label: 'Select', key: 'V', icon: <MousePointer2 size={19} />, edit: false },
  { tool: 'hand', label: 'Pan', key: 'H', icon: <Hand size={19} />, edit: false },
  { tool: 'pen', label: 'Pen', key: 'P', icon: <Pen size={19} />, edit: true },
  { tool: 'highlighter', label: 'Highlighter', key: 'I', icon: <Highlighter size={19} />, edit: true },
  { tool: 'eraser', label: 'Eraser', key: 'E', icon: <Eraser size={19} />, edit: true },
  { tool: 'text', label: 'Text', key: 'T', icon: <Type size={19} />, edit: true },
  { tool: 'sticky', label: 'Sticky note', key: 'S', icon: <StickyNote size={19} />, edit: true },
  { tool: 'connector', label: 'Connector', key: 'C', icon: <Spline size={19} />, edit: true },
];

export const TOOL_SHORTCUTS: Record<string, Tool> = Object.fromEntries(TOOLS.map((t) => [t.key.toLowerCase(), t.tool]));

interface Props {
  tool: Tool;
  onTool(tool: Tool): void;
  canEdit: boolean;
  libraryOpen: boolean;
  onToggleLibrary(): void;
  options: ToolOptions;
  onOptions(options: ToolOptions): void;
}

export function Toolbar({ tool, onTool, canEdit, libraryOpen, onToggleLibrary, options, onOptions }: Props) {
  return (
    <div className="toolbar-wrap">
      <nav className="toolbar" aria-label="Tools">
        {TOOLS.map((t) => (
          <IconButton
            key={t.tool}
            label={t.label}
            shortcut={t.key}
            active={tool === t.tool}
            disabled={t.edit && !canEdit}
            onClick={() => onTool(t.tool)}
            className="tooltip-right"
          >
            {t.icon}
          </IconButton>
        ))}
        <div className="toolbar-sep" />
        <IconButton
          label="Component library"
          shortcut="L"
          active={libraryOpen}
          disabled={!canEdit}
          onClick={onToggleLibrary}
          className="tooltip-right"
          aria-expanded={libraryOpen}
        >
          <LayoutGrid size={19} />
        </IconButton>
      </nav>

      {canEdit && (tool === 'pen' || tool === 'highlighter') && (
        <div className="tool-options" aria-label={`${tool} options`} role="group">
          <span className="tool-options-title">{tool === 'pen' ? 'Pen' : 'Highlighter'}</span>
          <div className="swatches">
            {(tool === 'pen' ? INK_COLORS : HIGHLIGHT_COLORS).map((c) => {
              const selected = tool === 'pen' ? options.penColor === c : options.highlighterColor === c;
              return (
                <button
                  key={c}
                  type="button"
                  className={`swatch${selected ? ' selected' : ''}`}
                  style={{ background: c }}
                  aria-label={`Colour ${c}`}
                  aria-pressed={selected}
                  onClick={() => onOptions(tool === 'pen' ? { ...options, penColor: c } : { ...options, highlighterColor: c })}
                />
              );
            })}
          </div>
          <div className="segmented" role="radiogroup" aria-label="Width">
            {[2, 4, 8].map((w) => (
              <button
                key={w}
                type="button"
                role="radio"
                aria-checked={options.penWidth === w}
                aria-label={`Width ${w}`}
                className={options.penWidth === w ? 'active' : ''}
                onClick={() => onOptions({ ...options, penWidth: w })}
              >
                <span className="width-dot" style={{ width: w + 2, height: w + 2 }} />
              </button>
            ))}
          </div>
        </div>
      )}

      {canEdit && tool === 'connector' && (
        <div className="tool-options" role="group" aria-label="Connector options">
          <span className="tool-options-title">Connector</span>
          <div className="segmented" role="radiogroup" aria-label="Routing">
            {(['straight', 'elbow', 'curved'] as Routing[]).map((r) => (
              <button
                key={r}
                type="button"
                role="radio"
                aria-checked={options.connector.routing === r}
                className={options.connector.routing === r ? 'active' : ''}
                onClick={() => onOptions({ ...options, connector: { ...options.connector, routing: r } })}
              >
                {r}
              </button>
            ))}
          </div>
          <p className="hint">Drag from one component to another.</p>
        </div>
      )}
    </div>
  );
}
