import { useState } from 'react';
import { X } from 'lucide-react';
import { CATEGORIES, COMPONENTS, type ComponentDef } from '../../canvas/catalog';
import type { ComponentType } from '../../canvas/types';
import { COMPONENT_DRAG_TYPE } from '../canvas/CanvasView';
import { COMPONENT_ICONS } from '../canvas/icons';

function Preview({ def }: { def: ComponentDef }) {
  const Icon = def.icon ? COMPONENT_ICONS[def.icon] : null;
  if (Icon) return <Icon size={20} color={def.accent} aria-hidden />;
  const common = { fill: def.fill === 'transparent' ? 'none' : def.fill, stroke: def.accent, strokeWidth: 1.5 };
  return (
    <svg width={22} height={18} viewBox="0 0 22 18" aria-hidden>
      {def.shape === 'ellipse' ? (
        <ellipse cx={11} cy={9} rx={10} ry={7} {...common} />
      ) : def.shape === 'text' ? (
        <text x={4} y={14} fontSize={14} fontWeight={700} fill={def.accent}>
          T
        </text>
      ) : def.shape === 'boundary' ? (
        <rect x={1} y={1} width={20} height={16} rx={3} {...common} strokeDasharray="3 2" />
      ) : (
        <rect x={1} y={2} width={20} height={14} rx={def.shape === 'rounded' ? 5 : def.shape === 'sticky' ? 1 : 2} {...common} />
      )}
    </svg>
  );
}

export function ComponentLibrary({ onAdd, onClose }: { onAdd(type: ComponentType): void; onClose(): void }) {
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const matches = (c: ComponentDef) => !q || c.name.toLowerCase().includes(q) || c.category.toLowerCase().includes(q);

  return (
    <aside className="library" aria-label="Component library">
      <header>
        <h2>Components</h2>
        <button type="button" className="icon-button" aria-label="Close component library" onClick={onClose}>
          <X size={16} />
        </button>
      </header>
      <input className="library-search" type="search" placeholder="Search components" aria-label="Search components" value={query} onChange={(e) => setQuery(e.target.value)} />
      <p className="hint">Click to add at the centre, or drag onto the canvas.</p>
      <div className="library-scroll">
        {CATEGORIES.map((cat) => {
          const items = COMPONENTS.filter((c) => c.category === cat && matches(c));
          if (items.length === 0) return null;
          return (
            <section key={cat}>
              <h3>{cat}</h3>
              <div className="library-grid">
                {items.map((c) => (
                  <button
                    key={c.type}
                    type="button"
                    className="library-item"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData(COMPONENT_DRAG_TYPE, c.type);
                      e.dataTransfer.effectAllowed = 'copy';
                    }}
                    onClick={() => onAdd(c.type)}
                    aria-label={`Add ${c.name}`}
                  >
                    <Preview def={c} />
                    <span>{c.name}</span>
                  </button>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </aside>
  );
}
