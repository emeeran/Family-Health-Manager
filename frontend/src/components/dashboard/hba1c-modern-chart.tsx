import { useState } from "react";

interface ChartRow {
  date: string;
  [memberName: string]: string | number;
}

interface Hba1cModernChartProps {
  rows: ChartRow[];
  members: string[];
}

const COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ec4899"];

export function Hba1cModernChart({ rows, members }: Hba1cModernChartProps) {
  const W = 600;
  const H = 200;
  const pad = { top: 12, right: 12, bottom: 24, left: 32 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const yMin = 3;
  const yMax =
    Math.max(14, ...rows.flatMap((r) => members.map((m) => Number(r[m] || 0))).filter(Boolean)) + 1;

  const toX = (i: number) => pad.left + (i / Math.max(rows.length - 1, 1)) * plotW;
  const toY = (v: number) => pad.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

  const yTicks = [4, 5, 5.7, 6, 6.5, 7, 8, 10, 12, 14].filter((v) => v >= yMin && v <= yMax);

  const hovered = hoveredIdx !== null ? rows[hoveredIdx] : null;

  return (
    <div className="relative w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        onMouseLeave={() => setHoveredIdx(null)}
      >
        {/* Threshold lines */}
        <line
          x1={pad.left}
          y1={toY(5.7)}
          x2={pad.left + plotW}
          y2={toY(5.7)}
          stroke="#f59e0b"
          strokeWidth={1}
          strokeDasharray="4 3"
          opacity={0.5}
        />
        <text
          x={pad.left + plotW - 2}
          y={toY(5.7) - 3}
          textAnchor="end"
          fontSize={8}
          fill="#d97706"
          opacity={0.7}
        >
          Pre 5.7%
        </text>
        <line
          x1={pad.left}
          y1={toY(6.5)}
          x2={pad.left + plotW}
          y2={toY(6.5)}
          stroke="#ef4444"
          strokeWidth={1}
          strokeDasharray="4 3"
          opacity={0.5}
        />
        <text
          x={pad.left + plotW - 2}
          y={toY(6.5) - 3}
          textAnchor="end"
          fontSize={8}
          fill="#dc2626"
          opacity={0.7}
        >
          DM 6.5%
        </text>

        {/* Grid */}
        {yTicks.map((v) => (
          <line
            key={v}
            x1={pad.left}
            y1={toY(v)}
            x2={pad.left + plotW}
            y2={toY(v)}
            stroke="currentColor"
            strokeOpacity={0.05}
          />
        ))}

        {/* Y labels */}
        {yTicks.map((v) => (
          <text
            key={v}
            x={pad.left - 5}
            y={toY(v) + 3}
            textAnchor="end"
            fontSize={9}
            fill="currentColor"
            opacity={0.35}
          >
            {v}
          </text>
        ))}

        {/* X labels */}
        {rows.map((row, i) => {
          const step = rows.length <= 8 ? 1 : rows.length <= 15 ? 2 : 3;
          if (i % step !== 0 && i !== rows.length - 1) return null;
          return (
            <text
              key={i}
              x={toX(i)}
              y={H - 3}
              textAnchor="middle"
              fontSize={9}
              fill="currentColor"
              opacity={0.35}
            >
              {String(row.date).slice(5)}
            </text>
          );
        })}

        {/* Lines */}
        {members.map((name, mi) => {
          const pts = rows
            .map((row, i) => {
              const v = Number(row[name]);
              return !isNaN(v) && v > 0 ? { x: toX(i), y: toY(v), i } : null;
            })
            .filter(Boolean) as { x: number; y: number; i: number }[];
          if (pts.length < 2) return null;
          const d = pts.map((p, j) => (j === 0 ? "M" : "L") + `${p.x},${p.y}`).join(" ");
          return (
            <g key={name}>
              <path
                d={d}
                fill="none"
                stroke={COLORS[mi % COLORS.length]}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {pts.map((p) => (
                <circle
                  key={p.i}
                  cx={p.x}
                  cy={p.y}
                  r={3}
                  fill={COLORS[mi % COLORS.length]}
                  stroke="white"
                  strokeWidth={1.5}
                  onMouseEnter={() => setHoveredIdx(p.i)}
                  style={{ cursor: "pointer" }}
                />
              ))}
            </g>
          );
        })}

        {/* Hover guide */}
        {hoveredIdx !== null && (
          <line
            x1={toX(hoveredIdx)}
            y1={pad.top}
            x2={toX(hoveredIdx)}
            y2={pad.top + plotH}
            stroke="currentColor"
            strokeOpacity={0.12}
            strokeDasharray="3 2"
          />
        )}
      </svg>

      {/* Tooltip */}
      {hovered && (
        <div
          className="absolute top-1 pointer-events-none rounded-lg border bg-popover/95 backdrop-blur-sm px-3 py-2 shadow-md text-xs z-10"
          style={{
            left: `${((toX(hoveredIdx!) - pad.left) / plotW) * 100}%`,
            transform: hoveredIdx! > rows.length / 2 ? "translateX(-110%)" : "translateX(10%)",
          }}
        >
          <p className="font-medium text-muted-foreground mb-0.5">{String(hovered.date)}</p>
          {members.map((name, i) => {
            const v = hovered[name];
            if (!v || Number(v) <= 0) return null;
            return (
              <div key={name} className="flex items-center gap-1.5">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ backgroundColor: COLORS[i % COLORS.length] }}
                />
                <span>
                  {name}: {v}%
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Legend */}
      {members.length > 1 && (
        <div className="flex items-center gap-4 mt-1 justify-center">
          {members.map((name, i) => (
            <div key={name} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span
                className="inline-block w-3 h-0.5 rounded"
                style={{ backgroundColor: COLORS[i % COLORS.length] }}
              />
              {name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
