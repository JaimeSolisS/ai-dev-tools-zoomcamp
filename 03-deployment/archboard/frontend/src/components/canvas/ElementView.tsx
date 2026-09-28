import { memo } from 'react';
import { getComponent } from '../../canvas/catalog';
import { arrowHead, connectorGeometry, strokePath, type ElementIndex } from '../../canvas/geometry';
import type { CanvasElement, ConnectorElement, ShapeElement, StrokeElement } from '../../canvas/types';
import { COMPONENT_ICONS } from './icons';

interface Props {
  element: CanvasElement;
  index: ElementIndex;
  /** Hide the label while it is being edited in place. */
  editing?: boolean;
}

export const ElementView = memo(function ElementView({ element, index, editing }: Props) {
  switch (element.kind) {
    case 'shape':
      return <ShapeView el={element} editing={editing} />;
    case 'connector':
      return <ConnectorView el={element} index={index} editing={editing} />;
    case 'stroke':
      return <StrokeView el={element} />;
  }
});

function describe(el: CanvasElement): string {
  if (el.kind === 'shape') return `${getComponent(el.componentType).name}: ${el.label || 'untitled'}`;
  if (el.kind === 'connector') return `Connector${el.label ? `: ${el.label}` : ''}`;
  return el.tool === 'highlighter' ? 'Highlighter stroke' : 'Pen stroke';
}

function ShapeView({ el, editing }: { el: ShapeElement; editing?: boolean }) {
  const def = getComponent(el.componentType);
  const fill = el.fill ?? def.fill;
  const { x, y, w, h } = el;
  const Icon = def.icon ? COMPONENT_ICONS[def.icon] : null;
  const iconSize = Math.min(28, h * 0.4, w * 0.3);

  let body: JSX.Element;
  switch (def.shape) {
    case 'ellipse':
      body = <ellipse cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} fill={fill} stroke={def.accent} strokeWidth={1.5} />;
      break;
    case 'cylinder': {
      const ry = Math.min(12, h / 6);
      body = (
        <g>
          <path
            d={`M${x} ${y + ry} A${w / 2} ${ry} 0 0 1 ${x + w} ${y + ry} V${y + h - ry} A${w / 2} ${ry} 0 0 1 ${x} ${y + h - ry} Z`}
            fill={fill}
            stroke={def.accent}
            strokeWidth={1.5}
          />
          <path d={`M${x} ${y + ry} A${w / 2} ${ry} 0 0 0 ${x + w} ${y + ry}`} fill="none" stroke={def.accent} strokeWidth={1.5} />
        </g>
      );
      break;
    }
    case 'queue': {
      const cells = 3;
      const cw = Math.min(14, w / 8);
      body = (
        <g>
          <rect x={x} y={y} width={w} height={h} rx={6} fill={fill} stroke={def.accent} strokeWidth={1.5} />
          {Array.from({ length: cells }, (_, i) => (
            <line
              key={i}
              x1={x + w - cw * (i + 1)}
              x2={x + w - cw * (i + 1)}
              y1={y + 6}
              y2={y + h - 6}
              stroke={def.accent}
              strokeOpacity={0.5}
            />
          ))}
        </g>
      );
      break;
    }
    case 'text':
      body = <rect x={x} y={y} width={w} height={h} fill="transparent" />;
      break;
    case 'sticky':
      body = (
        <g>
          <rect x={x + 2} y={y + 3} width={w} height={h} fill="rgba(15,23,42,0.12)" rx={2} />
          <rect x={x} y={y} width={w} height={h} fill={fill} stroke="rgba(15,23,42,0.15)" rx={2} />
        </g>
      );
      break;
    case 'boundary':
      body = (
        <rect
          x={x}
          y={y}
          width={w}
          height={h}
          rx={12}
          fill="rgba(100,116,139,0.04)"
          stroke={def.accent}
          strokeWidth={1.5}
          strokeDasharray="8 6"
          pointerEvents="visibleStroke"
          className="boundary-edge"
        />
      );
      break;
    default:
      body = (
        <rect
          x={x}
          y={y}
          width={w}
          height={h}
          rx={def.shape === 'rounded' ? 14 : 4}
          fill={fill}
          stroke={def.accent}
          strokeWidth={1.5}
        />
      );
  }

  const labelClass =
    def.shape === 'sticky' ? 'shape-label sticky' : def.shape === 'text' ? 'shape-label text' : def.shape === 'boundary' ? 'shape-label boundary' : 'shape-label';
  const labelBox =
    def.shape === 'boundary'
      ? { x: x + 8, y: y + 6, w: Math.max(40, w - 16), h: 26 }
      : Icon
        ? { x: x + 6, y: y + iconSize + 8, w: w - 12, h: Math.max(14, h - iconSize - 12) }
        : { x: x + 6, y: y + 4, w: w - 12, h: h - 8 };

  return (
    <g role="img" aria-label={describe(el)}>
      {body}
      {Icon && (
        <Icon x={x + w / 2 - iconSize / 2} y={y + 6} width={iconSize} height={iconSize} color={def.accent} strokeWidth={1.75} aria-hidden />
      )}
      {!editing && (
        <foreignObject
          x={labelBox.x}
          y={labelBox.y}
          width={Math.max(1, labelBox.w)}
          height={Math.max(1, labelBox.h)}
          pointerEvents={def.shape === 'boundary' ? 'auto' : 'none'}
        >
          <div className={labelClass} style={{ color: def.shape === 'sticky' ? '#422006' : '#0f172a' }}>
            {el.label}
          </div>
        </foreignObject>
      )}
      {el.description && !editing && def.shape !== 'text' && def.shape !== 'sticky' && (
        <title>{el.description}</title>
      )}
    </g>
  );
}

function ConnectorView({ el, index, editing }: { el: ConnectorElement; index: ElementIndex; editing?: boolean }) {
  const g = connectorGeometry(el, index);
  const size = 7 + el.width * 2;
  const labelWidth = Math.max(24, el.label.length * 7 + 14);
  return (
    <g role="img" aria-label={describe(el)}>
      <path d={g.path} fill="none" stroke="transparent" strokeWidth={14} className="hit" />
      <path
        d={g.path}
        fill="none"
        stroke={el.color}
        strokeWidth={el.width}
        strokeDasharray={el.dashed ? `${el.width * 4} ${el.width * 3}` : undefined}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {el.arrowEnd && <path d={arrowHead(g.end, g.endAngle, size)} fill={el.color} stroke={el.color} strokeLinejoin="round" />}
      {el.arrowStart && <path d={arrowHead(g.start, g.startAngle, size)} fill={el.color} stroke={el.color} strokeLinejoin="round" />}
      {el.label && !editing && (
        <g>
          <rect x={g.mid.x - labelWidth / 2} y={g.mid.y - 11} width={labelWidth} height={22} rx={5} fill="#ffffff" stroke="#e2e8f0" />
          <text x={g.mid.x} y={g.mid.y + 4} textAnchor="middle" className="connector-label">
            {el.label}
          </text>
        </g>
      )}
    </g>
  );
}

function StrokeView({ el }: { el: StrokeElement }) {
  const d = strokePath(el.points);
  return (
    <g role="img" aria-label={describe(el)}>
      <path d={d} fill="none" stroke="transparent" strokeWidth={Math.max(12, el.width + 8)} strokeLinecap="round" className="hit" />
      <path
        d={d}
        fill="none"
        stroke={el.color}
        strokeWidth={el.width}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={el.tool === 'highlighter' ? 0.35 : 1}
      />
    </g>
  );
}

export { describe as describeElement };
