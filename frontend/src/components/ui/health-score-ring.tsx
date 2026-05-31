import { memo } from "react";

export function scoreColor(score: number): string {
  if (score >= 75) return "#16a34a"; // green-600
  if (score >= 50) return "#d97706"; // amber-600
  return "#dc2626"; // red-600
}

export function scoreTextColor(score: number): string {
  if (score >= 75) return "text-green-600 dark:text-green-400";
  if (score >= 50) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

interface HealthScoreRingProps {
  score: number;
  initials?: string;
  size?: number;
  strokeWidth?: number;
}

export const HealthScoreRing = memo(function HealthScoreRing({
  score,
  initials,
  size = 48,
  strokeWidth = 3,
}: HealthScoreRingProps) {
  const r = (size - strokeWidth * 2) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = scoreColor(score);
  const cx = size / 2;

  return (
    <div className="relative shrink-0 select-none" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="shrink-0">
        <circle
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-muted/20"
        />
        <circle
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cx})`}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {initials ? (
          <span className="text-[10px] font-bold text-foreground/70">{initials}</span>
        ) : (
          <span className="font-bold leading-none" style={{ color, fontSize: size * 0.28 }}>
            {score}
          </span>
        )}
      </div>
    </div>
  );
});
