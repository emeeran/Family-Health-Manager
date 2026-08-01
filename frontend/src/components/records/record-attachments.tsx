import { useRef, useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  Paperclip,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Upload,
  Printer,
} from "lucide-react";
import {
  uploadAttachment,
  getAttachmentBlob,
  getAttachmentThumbnailUrl,
} from "@/lib/api/attachments";
import { pickFiles } from "@/lib/file-picker";
import { toast } from "sonner";
import type { AttachmentBrief } from "@/lib/types/health-record";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface RecordAttachmentsProps {
  recordId: string;
  attachments: AttachmentBrief[];
  compact?: boolean;
  onAttachmentsChanged?: () => void;
}

export function RecordAttachments({
  recordId,
  attachments,
  compact,
  onAttachmentsChanged,
}: RecordAttachmentsProps) {
  const [uploading, setUploading] = useState(false);

  async function onPickFile() {
    const files = await pickFiles({ extensions: ["pdf", "jpg", "jpeg", "png", "webp"] });
    const file = files[0];
    if (!file) return;

    setUploading(true);
    try {
      await uploadAttachment(recordId, file);
      toast.success("File attached");
      onAttachmentsChanged?.();
    } catch {
      toast.error("Failed to attach file");
    } finally {
      setUploading(false);
    }
  }

  const hasAttachments = attachments.length > 0;

  // ── Compact mode (quick view) ──
  if (compact) {
    return (
      <div className="mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Paperclip className="h-3 w-3" />
          Original Document{attachments.length > 1 ? "s" : ""}
        </p>

        {hasAttachments ? (
          <div className="space-y-1.5">
            {attachments.map((att) => (
              <button
                key={att.id}
                type="button"
                onClick={async () => {
                  try {
                    const url = await getAttachmentBlob(att.id);
                    window.open(url, "_blank");
                  } catch {
                    toast.error("Failed to open attachment");
                  }
                }}
                className="flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400 hover:underline rounded px-2 py-1 hover:bg-muted/50 text-left w-full"
              >
                {att.mime_type.startsWith("image/") ? (
                  <ImageIcon className="h-3.5 w-3.5 shrink-0" />
                ) : (
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                )}
                <span className="truncate">{att.file_name}</span>
              </button>
            ))}
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-1.5 text-xs"
            onClick={onPickFile}
            disabled={uploading}
          >
            <Upload className="h-3 w-3" />
            {uploading ? "Uploading..." : "Attach Original"}
          </Button>
        )}
      </div>
    );
  }

  // ── Full mode (detail page) ──
  return (
    <div className="border-t border-gray-200 dark:border-gray-700 pt-4 print:hidden">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-1.5">
        <Paperclip className="h-3.5 w-3.5" />
        Original Document{attachments.length > 1 ? "s" : ""}
      </p>

      {hasAttachments ? (
        <div className="space-y-2">
          {attachments.map((att) => (
            <AttachmentRow key={att.id} attachment={att} />
          ))}
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={onPickFile}
          disabled={uploading}
        >
          <Upload className="h-3.5 w-3.5" />
          {uploading ? "Uploading..." : "Attach Original"}
        </Button>
      )}
    </div>
  );
}

function AttachmentRow({ attachment }: { attachment: AttachmentBrief }) {
  const isImage = attachment.mime_type.startsWith("image/");
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const blobUrlsRef = useRef<Set<string>>(new Set());

  // Track all created blob URLs for cleanup on unmount
  const trackBlobUrl = useCallback((url: string) => {
    blobUrlsRef.current.add(url);
    return url;
  }, []);

  // Revoke all tracked blob URLs on unmount
  useEffect(() => {
    const tracked = blobUrlsRef.current;
    return () => {
      for (const url of tracked) {
        URL.revokeObjectURL(url);
      }
      tracked.clear();
    };
  }, []);

  // Show the server-generated thumbnail (small WebP/PNG) directly as an <img>
  // src — fetching the full-resolution original just to render a 56px preview
  // downloaded megabytes and allocated a blob URL per row.
  useEffect(() => {
    if (!isImage) return;
    setThumbnailUrl(getAttachmentThumbnailUrl(attachment.id));
  }, [isImage, attachment.id]);

  async function openAttachment() {
    try {
      const url = await getAttachmentBlob(attachment.id);
      trackBlobUrl(url);
      window.open(url, "_blank");
    } catch {
      toast.error("Failed to open attachment");
    }
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
      {isImage ? (
        <button type="button" onClick={openAttachment} className="shrink-0">
          <div className="h-14 w-14 rounded bg-muted flex items-center justify-center overflow-hidden">
            {thumbnailUrl ? (
              <img
                src={thumbnailUrl}
                alt={attachment.file_name}
                loading="lazy"
                className="h-14 w-14 object-cover rounded"
              />
            ) : (
              <ImageIcon className="h-6 w-6 text-muted-foreground" />
            )}
          </div>
        </button>
      ) : (
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded bg-muted">
          <FileText className="h-6 w-6 text-muted-foreground" />
        </div>
      )}

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{attachment.file_name}</p>
        <p className="text-xs text-muted-foreground">
          {formatFileSize(attachment.file_size)} ·{" "}
          {attachment.mime_type.split("/")[1]?.toUpperCase()}
        </p>
      </div>

      <div className="flex gap-1.5 shrink-0">
        <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={openAttachment}>
          <ExternalLink className="h-3 w-3" />
          View
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs gap-1"
          onClick={async () => {
            try {
              const url = await getAttachmentBlob(attachment.id);
              trackBlobUrl(url);
              const w = window.open(url, "_blank");
              if (w) w.onload = () => w.print();
            } catch {
              toast.error("Failed to open attachment");
            }
          }}
        >
          <Printer className="h-3 w-3" />
          Print
        </Button>
      </div>
    </div>
  );
}
