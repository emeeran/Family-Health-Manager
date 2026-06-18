/**
 * Non-modal fly-out that previews the original staged upload beside the form.
 *
 * Deliberately not a modal Sheet/Dialog: it has no backdrop and doesn't trap
 * focus, so the user keeps typing into the entry fields while referencing the
 * source document. Fixed to the right of the viewport; close via the button or
 * Escape. The src URL is same-origin with cookie auth, so <img>/<iframe> work
 * directly (no blob fetch needed).
 */
import { useEffect } from "react";
import { X } from "lucide-react";
import { API_BASE } from "../record-form-utils";

interface StagingFileViewerProps {
  memberId: string;
  stagingId: string;
  fileName: string;
  onClose: () => void;
}

export function StagingFileViewer({
  memberId,
  stagingId,
  fileName,
  onClose,
}: StagingFileViewerProps) {
  const url = `${API_BASE}/members/${memberId}/records/staging/${encodeURIComponent(stagingId)}`;
  const isPdf = /\.pdf$/i.test(fileName);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed top-0 right-0 z-40 flex h-full w-[42%] min-w-[300px] max-w-2xl flex-col border-l bg-background shadow-2xl">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <span className="truncate text-xs font-medium" title={fileName}>
          {fileName}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Close preview"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 overflow-auto bg-muted/30 p-2">
        {isPdf ? (
          <iframe src={url} title={fileName} className="h-full w-full border-0 bg-white" />
        ) : (
          <img src={url} alt={fileName} className="mx-auto max-h-full max-w-full object-contain" />
        )}
      </div>
    </div>
  );
}
