import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Format an ISO date string as DD-MM-YYYY — deterministic across server/client. */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${day}-${m}-${y}`;
}

/** Convert DD-MM-YYYY → YYYY-MM-DD for API submission. Returns original if already ISO. */
export function toISODate(val: string): string {
  const dmy = val.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if (dmy) return `${dmy[3]}-${dmy[2]}-${dmy[1]}`;
  return val;
}

/** Convert YYYY-MM-DD → DD-MM-YYYY for display. */
export function toDisplayDate(val: string): string {
  const iso = val.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) return `${iso[3]}-${iso[2]}-${iso[1]}`;
  return val;
}

/** Compute age in years from a date-of-birth string. */
export function computeAge(dob: string): number {
  const today = new Date();
  const birth = new Date(dob);
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
  return age;
}

/** Format age as `"42y"` from an optional DOB string, or `null` if absent/invalid. */
export function formatAge(dob: string | null | undefined): string | null {
  if (!dob) return null;
  const age = computeAge(dob);
  return age >= 0 ? `${age}y` : null;
}

/** Format an ISO date string as a human-friendly relative label. */
export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const absDays = Math.abs(Math.round(diffMs / (1000 * 60 * 60 * 24)));

  if (absDays === 0) {
    const hours = Math.abs(Math.round(diffMs / (1000 * 60 * 60)));
    if (hours === 0) {
      const mins = Math.abs(Math.round(diffMs / (1000 * 60)));
      return mins <= 1 ? "Just now" : `${mins}m ago`;
    }
    return diffMs < 0 ? (hours === 1 ? "1h ago" : `${hours}h ago`) : "Today";
  }
  if (diffMs < 0) {
    if (absDays === 1) return "Yesterday";
    return `${absDays}d ago`;
  }
  if (absDays === 1) return "Tomorrow";
  return `In ${absDays} days`;
}
