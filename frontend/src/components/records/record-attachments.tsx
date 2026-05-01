import { useRef, useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  Paperclip,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Upload,
  Printer,
} from "lucide-react";
import { uploadAttachment, getAttachmentBlob } from "@/lib/api/attachments";
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
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
      // Reset input so same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = "";
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
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            <Upload className="h-3 w-3" />
            {uploading ? "Uploading..." : "Attach Original"}
          </Button>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.pdf"
          className="hidden"
          onChange={handleUpload}
        />
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
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
        >
          <Upload className="h-3.5 w-3.5" />
          {uploading ? "Uploading..." : "Attach Original"}
        </Button>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf"
        className="hidden"
        onChange={handleUpload}
      />
    </div>
  );
}

function AttachmentRow({ attachment }: { attachment: AttachmentBrief }) {
  const isImage = attachment.mime_type.startsWith("image/");
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  async function openAttachment() {
    try {
      const url = await getAttachmentBlob(attachment.id);
      setBlobUrl(url);
      window.open(url, "_blank");
    } catch {
      toast.error("Failed to open attachment");
    }
  }

  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
      {isImage ? (
        <button type="button" onClick={openAttachment} className="shrink-0">
          <div className="h-14 w-14 rounded bg-muted flex items-center justify-center">
            <ImageIcon className="h-6 w-6 text-muted-foreground" />
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
