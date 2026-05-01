import { useId } from "react";

interface DawnstarLogoProps {
  className?: string;
  variant: "gradient" | "white" | "gold";
}

export function DawnstarLogo({ className = "h-6 w-6", variant }: DawnstarLogoProps) {
  const uid = useId();
  const gradId = `${uid}-grad`;
  const glowId = `${uid}-glow`;

  const mainFill =
    variant === "white" ? "white" : variant === "gold" ? "#FF6B35" : `url(#${gradId})`;
  const strokeColor = variant === "white" ? "white" : "#333333";

  return (
    <svg className={className} viewBox="0 0 100 100" fill="none">
      <defs>
        <radialGradient id={gradId} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#FF6B35" />
          <stop offset="100%" stopColor="#FFA500" />
        </radialGradient>
        <filter id={glowId} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Main 5-point star with stroke and subtle glow */}
      <path
        d="M50,10 L58,32 L78,32 L62,46 L68,70 L50,55 L32,70 L38,46 L22,32 L42,32 Z"
        fill={mainFill}
        stroke={strokeColor}
        strokeWidth="1"
        filter={`url(#${glowId})`}
      />

      {/* Swoosh — curves from bottom-left valley outward to the left */}
      <path
        d="M32,70 Q26,74 24,78 Q22,82 18,84"
        fill="none"
        stroke={strokeColor}
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* Circuit line 1 — short curve from bottom-right valley */}
      <path
        d="M68,70 Q72,74 75,78"
        fill="none"
        stroke={strokeColor}
        strokeWidth="1"
        strokeLinecap="round"
      />
      {/* Dot at end of circuit line 1 */}
      <circle cx="75" cy="78" r="2" fill={mainFill} />

      {/* Circuit line 2 — longer curve from top-right valley */}
      <path
        d="M62,46 Q68,48 72,52 Q76,56 82,58"
        fill="none"
        stroke={strokeColor}
        strokeWidth="1"
        strokeLinecap="round"
      />
    </svg>
  );
}
