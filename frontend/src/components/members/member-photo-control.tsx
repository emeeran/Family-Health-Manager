import { useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { Camera, Loader2, Trash2 } from "lucide-react";

import { deleteMemberPhoto, uploadMemberPhoto } from "@/lib/api/members";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { MemberAvatar } from "./member-avatar";

const MAX_PHOTO_SIZE = 10 * 1024 * 1024; // 10 MB
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

/** Profile-photo control for the member detail header: shows the avatar with a
 *  small camera badge (upload/replace) and, when a photo exists, a remove
 *  badge. Both badges are hidden until the avatar is hovered or focused. */
export function MemberPhotoControl({
  member,
  size = 56,
}: {
  member: FamilyMemberResponse;
  size?: number;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const { mutate } = useSWRConfig();

  const refresh = () =>
    Promise.all([mutate(`member-detail-${member.id}`), mutate("members"), mutate("dashboard")]);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (inputRef.current) inputRef.current.value = "";
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      toast.error("Photo must be a JPEG, PNG, or WebP image");
      return;
    }
    if (file.size > MAX_PHOTO_SIZE) {
      toast.error("Photo must be 10 MB or smaller");
      return;
    }
    setBusy(true);
    try {
      await uploadMemberPhoto(member.id, file);
      await refresh();
      toast.success(member.has_photo ? "Photo updated" : "Photo added");
    } catch {
      toast.error("Failed to upload photo");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove() {
    setBusy(true);
    try {
      await deleteMemberPhoto(member.id);
      await refresh();
      toast.success("Photo removed");
    } catch {
      toast.error("Failed to remove photo");
    } finally {
      setBusy(false);
    }
  }

  // Badges are hidden until the control is hovered (desktop) or focused (keyboard).
  const badgeReveal =
    "opacity-0 transition-opacity duration-150 group-hover/photo:opacity-100 focus-visible:opacity-100";

  return (
    <div className="group/photo relative shrink-0" style={{ width: size, height: size }}>
      <MemberAvatar member={member} size={size} />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={busy}
        aria-label={member.has_photo ? "Change photo" : "Add photo"}
        title={member.has_photo ? "Change photo" : "Add photo"}
        className={`absolute -bottom-1 -right-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground shadow ring-2 ring-background hover:bg-primary/90 disabled:opacity-100 ${badgeReveal}`}
      >
        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Camera className="h-3 w-3" />}
      </button>

      {member.has_photo && !busy && (
        <button
          type="button"
          onClick={handleRemove}
          aria-label="Remove photo"
          title="Remove photo"
          className={`absolute -bottom-1 -left-1 inline-flex h-6 w-6 items-center justify-center rounded-full bg-destructive text-white shadow ring-2 ring-background hover:bg-destructive/90 ${badgeReveal}`}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(",")}
        className="hidden"
        onChange={handleFile}
      />
    </div>
  );
}
