import { memo } from "react";
import { HealthScoreRing } from "@/components/ui/health-score-ring";
import { API_BASE_URL } from "@/lib/constants";
import type { FamilyMemberResponse } from "@/lib/types/member";

function getInitials(first: string, last: string): string {
  return (first[0] + (last ? last[0] : "")).toUpperCase();
}

/** Cookie-auth <img> URL for a member's photo thumbnail, cache-busted by the
 *  server-provided photo_updated_at so a changed photo reloads everywhere. */
export function memberPhotoUrl(member: FamilyMemberResponse): string {
  const v = member.photo_updated_at ? encodeURIComponent(member.photo_updated_at) : "";
  return `${API_BASE_URL}/members/${member.id}/photo${v ? `?v=${v}` : ""}`;
}

interface MemberAvatarProps {
  member: FamilyMemberResponse;
  /** When provided, the avatar renders inside a health-score ring (cards).
   *  Omit for a plain avatar (detail header, where the ring is separate). */
  score?: number;
  size?: number;
  className?: string;
}

/** Reusable member avatar. Shows the profile photo when present, else initials.
 *  In ring mode the photo fills the centre of the health-score ring. */
export const MemberAvatar = memo(function MemberAvatar({
  member,
  score,
  size = 48,
  className,
}: MemberAvatarProps) {
  const initials = getInitials(member.first_name, member.last_name);
  const imageUrl = member.has_photo ? memberPhotoUrl(member) : undefined;

  if (score !== undefined) {
    return <HealthScoreRing score={score} initials={initials} imageUrl={imageUrl} size={size} />;
  }

  return (
    <div
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-primary/10 font-bold text-primary ${className ?? ""}`}
      style={{ width: size, height: size }}
    >
      {imageUrl ? (
        <img src={imageUrl} alt="" loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <span style={{ fontSize: size * 0.36 }}>{initials}</span>
      )}
    </div>
  );
});
