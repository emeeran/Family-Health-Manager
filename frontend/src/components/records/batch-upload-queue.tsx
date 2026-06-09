import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { batchExtract, checkFilenames, createRecord } from "@/lib/api/records";
import { ALLOWED_MIME_TYPES, MAX_FILE_SIZE } from "@/lib/constants";
import { BatchRecordCard, type CardStatus } from "./batch-record-card";
import type { BatchExtractionItem } from "@/lib/types/health-record";
import type { RecordType } from "@/lib/types/enums";
import {
  Upload,
  FolderOpen,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  FileText,
  X,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";

type Phase = "upload" | "checking" | "extracting" | "review" | "done";

interface BatchUploadQueueProps {
  memberId: string;
  onComplete?: () => void;
  /** Files pre-loaded from redirect (e.g. from single-record page) */
  initialFiles?: File[];
}

const ACCEPTED_EXTENSIONS = new Set([".pdf", ".jpg", ".jpeg", ".png"]);
const STORAGE_KEY = (mid: string) => `batch_extraction_${mid}`;

function isValidFile(file: File): string | null {
  if (!ALLOWED_MIME_TYPES.includes(file.type as (typeof ALLOWED_MIME_TYPES)[number])) {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED_EXTENSIONS.has(ext)) {
      return `Invalid file type: ${file.name}`;
    }
  }
  if (file.size > MAX_FILE_SIZE) {
    return `File too large (>25MB): ${file.name}`;
  }
  return null;
}

// ── Singleton background extraction manager ──
// Persists across component mounts/unmounts so extraction survives navigation.
const bgExtractors = new Map<
  string,
  {
    abort: AbortController;
    promise: Promise<BatchExtractionItem[]>;
    dirMode: boolean;
  }
>();

function getStoredExtractions(memberId: string): BatchExtractionItem[] | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY(memberId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function storeExtractions(memberId: string, items: BatchExtractionItem[]) {
  sessionStorage.setItem(STORAGE_KEY(memberId), JSON.stringify(items));
}

function clearStoredExtractions(memberId: string) {
  sessionStorage.removeItem(STORAGE_KEY(memberId));
}

export function hasBackgroundExtraction(memberId: string): boolean {
  return bgExtractors.has(memberId);
}

export function BatchUploadQueue({ memberId, onComplete, initialFiles }: BatchUploadQueueProps) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>("upload");
  const [files, setFiles] = useState<File[]>([]);
  const [extractions, setExtractions] = useState<BatchExtractionItem[]>([]);
  const [extractProgress, setExtractProgress] = useState(0);
  const [cardStatuses, setCardStatuses] = useState<Map<number, CardStatus>>(new Map());
  const [isDragOver, setIsDragOver] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [skippedFiles, setSkippedFiles] = useState<string[]>([]);
  const [isDirectoryMode, setIsDirectoryMode] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dirInputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(true);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Auto-start when files arrive via redirect from single-record page
  const initialFilesProcessed = useRef(false);
  useEffect(() => {
    if (initialFiles && initialFiles.length > 0 && !initialFilesProcessed.current) {
      initialFilesProcessed.current = true;
      addFiles(initialFiles);
    }
  }, [initialFiles]);

  // On mount: check for completed background extraction
  useEffect(() => {
    const bg = bgExtractors.get(memberId);
    if (bg) {
      // Extraction is still running — hook into it
      setPhase("extracting");
      setExtractProgress(50);
      bg.promise.then((items) => {
        if (!mountedRef.current) return;
        bgExtractors.delete(memberId);
        processExtractionResults(items, bg.dirMode);
      });
      return;
    }

    // No active extraction — check sessionStorage for completed results
    const stored = getStoredExtractions(memberId);
    if (stored && stored.length > 0) {
      clearStoredExtractions(memberId);
      setExtractions(stored);
      setPhase("review");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [memberId]);

  function addFiles(newFiles: FileList | File[]) {
    const arr = Array.from(newFiles);
    const valid: File[] = [];
    const errs: string[] = [];

    for (const f of arr) {
      const err = isValidFile(f);
      if (err) errs.push(err);
      else valid.push(f);
    }

    if (errs.length > 0) setErrors((prev) => [...prev, ...errs]);

    // Deduplicate by name + size
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const unique = valid.filter((f) => !existing.has(`${f.name}:${f.size}`));
      return [...prev, ...unique];
    });
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  // ── Process extraction results (duplicate detection + auto-save) ──
  async function processExtractionResults(allExtractions: BatchExtractionItem[], dirMode: boolean) {
    // Check for in-batch duplicates (same type + date + diagnosis)
    const seen = new Map<string, number>();
    const patched = allExtractions.map((item, idx) => {
      const ext = item.extracted;
      if (ext?.record_type && ext?.record_date && ext?.diagnosis) {
        const key = `${ext.record_type}|${ext.record_date}|${ext.diagnosis.toLowerCase().trim()}`;
        if (seen.has(key)) {
          const _prevIdx = seen.get(key)!;
          return { ...item, is_duplicate: true };
        } else {
          seen.set(key, idx);
        }
      }
      return item;
    });

    setExtractions(patched);
    setExtractProgress(100);

    // ── Auto-save in directory mode ──
    if (dirMode) {
      let savedN = 0;
      for (let i = 0; i < patched.length; i++) {
        const item = patched[i];
        if (item.error || !item.extracted || !item.staging_file_id) continue;

        try {
          const ext = item.extracted;
          const recordType = (ext.record_type || "misc_record") as RecordType;
          const recordDate = ext.record_date || new Date().toISOString().slice(0, 10);

          await createRecord(
            memberId,
            {
              record_type: recordType,
              record_date: recordDate,
              clinical_data: ext.clinical_data || "{}",
              diagnosis: ext.diagnosis || null,
              prescription_text: ext.prescription_text || null,
              next_review_date: ext.next_review_date || null,
              tags: ["To manually verify"],
            },
            item.staging_file_id,
            item.filename
          );

          savedN++;
          if (mountedRef.current) {
            setCardStatuses((prev) => {
              const next = new Map(prev);
              next.set(i, "saved");
              return next;
            });
          }
        } catch {
          // Leave for manual review
        }
      }

      if (mountedRef.current) {
        toast.success(
          `${savedN} record${savedN !== 1 ? "s" : ""} auto-saved with "To manually verify" tag`
        );
        setPhase("done");
      }
      return;
    }

    // ── Normal batch mode: go to review ──
    storeExtractions(memberId, patched);
    if (mountedRef.current) {
      setPhase("review");
    } else {
      // Component unmounted — show toast so user knows results are ready
      toast.success("Batch extraction complete! Return to Batch Upload to review.", {
        duration: 8000,
        action: {
          label: "View",
          onClick: () => navigate(`/people/${memberId}/records/batch`),
        },
      });
    }
  }

  // ── Core extraction logic — runs in background via ref ──
  async function handleExtractWithFiles(filesToExtract: File[], dirMode: boolean) {
    setPhase("extracting");
    setExtractProgress(5);

    // Chunk files into groups under 90MB to stay within server body limit
    const CHUNK_SIZE = 90 * 1024 * 1024;
    const chunks: File[][] = [];
    let currentChunk: File[] = [];
    let currentSize = 0;

    for (const f of filesToExtract) {
      if (currentSize + f.size > CHUNK_SIZE && currentChunk.length > 0) {
        chunks.push(currentChunk);
        currentChunk = [];
        currentSize = 0;
      }
      currentChunk.push(f);
      currentSize += f.size;
    }
    if (currentChunk.length > 0) chunks.push(currentChunk);

    const abortCtrl = new AbortController();

    const extractPromise = (async () => {
      let allExtractions: BatchExtractionItem[] = [];

      for (let c = 0; c < chunks.length; c++) {
        if (abortCtrl.signal.aborted) break;

        // Update progress: reserve 5–95% range across chunks
        const pct = 5 + Math.round(((c + 1) / chunks.length) * 90);
        if (mountedRef.current) setExtractProgress(pct);

        try {
          const result = await batchExtract(memberId, chunks[c]);
          allExtractions = allExtractions.concat(result.extractions);
        } catch (e) {
          const chunkErrors: BatchExtractionItem[] = chunks[c].map((f) => ({
            filename: f.name,
            staging_file_id: null,
            extracted: null,
            transcription: null,
            is_duplicate: false,
            duplicate_of_id: null,
            duplicate_of_diagnosis: null,
            error: e instanceof Error ? e.message : "Extraction failed",
            verification: null,
          }));
          allExtractions = allExtractions.concat(chunkErrors);
        }
      }

      return allExtractions;
    })();

    // Register as background task
    bgExtractors.set(memberId, { abort: abortCtrl, promise: extractPromise, dirMode });

    extractPromise.then((items) => {
      bgExtractors.delete(memberId);
      if (mountedRef.current) {
        processExtractionResults(items, dirMode);
      } else {
        // Component unmounted — store results and notify
        storeExtractions(memberId, items);
        if (!dirMode) {
          toast.success("Batch extraction complete! Return to Batch Upload to review.", {
            duration: 8000,
            action: {
              label: "View",
              onClick: () => navigate(`/people/${memberId}/records/batch`),
            },
          });
        }
      }
    });
  }

  async function handleExtract() {
    if (files.length === 0) return;
    await handleExtractWithFiles(files, false);
  }

  // ── Directory mode: check filenames then extract ──
  async function handleDirectoryCheck() {
    if (files.length === 0) return;

    setPhase("checking");

    try {
      const filenames = files.map((f) => f.name);
      const result = await checkFilenames(memberId, filenames);
      const existingSet = new Set(result.existing);
      const skipped = files.filter((f) => existingSet.has(f.name));
      const remaining = files.filter((f) => !existingSet.has(f.name));

      setSkippedFiles(skipped.map((f) => f.name));

      if (remaining.length === 0) {
        toast.info("All files already have records");
        setPhase("done");
        return;
      }

      // Update visible file list to show only new files
      setFiles(remaining);

      if (skipped.length > 0) {
        toast.info(
          `${skipped.length} file${skipped.length !== 1 ? "s" : ""} skipped (already have records)`
        );
      }

      await handleExtractWithFiles(remaining, true);
    } catch {
      // If check fails, fall through to regular extraction
      toast.warning("Could not check existing records — extracting all files");
      await handleExtractWithFiles(files, true);
    }
  }

  const handleStatusChange = useCallback((index: number, status: CardStatus) => {
    setCardStatuses((prev) => {
      const next = new Map(prev);
      next.set(index, status);
      return next;
    });
  }, []);

  const handleDelete = useCallback((index: number) => {
    setExtractions((prev) => prev.filter((_, i) => i !== index));
    setCardStatuses((prev) => {
      const next = new Map();
      prev.forEach((status, i) => {
        if (i < index) next.set(i, status);
        else if (i > index) next.set(i - 1, status);
      });
      return next;
    });
    toast.success("Record removed from queue");
  }, []);

  const { savedCount, skippedCount, dupCount, errorCount, pendingCount, allDone } = useMemo(() => {
    const savedCount = Array.from(cardStatuses.values()).filter((s) => s === "saved").length;
    const skippedCount = Array.from(cardStatuses.values()).filter((s) => s === "skipped").length;
    const dupCount = extractions.filter((e) => e.is_duplicate).length;
    const errorCount = extractions.filter((e) => !!e.error).length;
    const pendingCount = extractions.filter((_, i) => {
      const s = cardStatuses.get(i);
      return !s || s === "pending" || s === "editing" || s === "error";
    }).length;
    const allDone =
      extractions.length > 0 &&
      extractions.every((_, i) => {
        const s = cardStatuses.get(i);
        return s === "saved" || s === "skipped";
      });
    return { savedCount, skippedCount, dupCount, errorCount, pendingCount, allDone };
  }, [cardStatuses, extractions]);

  // Track which card to auto-expand (first pending)
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  // Auto-focus first pending card when entering review phase
  useEffect(() => {
    if (phase === "review" && activeIndex === null) {
      const firstPending = extractions.findIndex((_, i) => {
        const s = cardStatuses.get(i);
        return !s || s === "pending" || s === "error";
      });
      if (firstPending >= 0) setActiveIndex(firstPending);
    }
  }, [phase, activeIndex, extractions, cardStatuses]);

  // Auto-advance active index when current card is saved/skipped
  useEffect(() => {
    if (
      (activeIndex !== null && cardStatuses.get(activeIndex) === "saved") ||
      cardStatuses.get(activeIndex!) === "skipped"
    ) {
      const next = extractions.findIndex((item, i) => {
        if (i <= activeIndex!) return false;
        const s = cardStatuses.get(i);
        return !s || s === "pending" || s === "error";
      });
      setActiveIndex(next >= 0 ? next : null);
    }
  }, [cardStatuses, activeIndex, extractions]);

  function handleReviewNext() {
    const next = extractions.findIndex((_, i) => {
      const s = cardStatuses.get(i);
      return !s || s === "pending" || s === "error";
    });
    setActiveIndex(next >= 0 ? next : null);
  }

  // ── Upload Phase ──
  if (phase === "upload") {
    return (
      <div className="space-y-4">
        {/* Drop zone */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
          }}
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDragOver(true);
          }}
          onDragEnter={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDragOver(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDragOver(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setIsDragOver(false);
            if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
          }}
          className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors cursor-pointer ${
            isDragOver
              ? "border-blue-400 bg-blue-50/50"
              : "border-gray-300 hover:border-gray-400 hover:bg-gray-50/50"
          }`}
        >
          <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
          <p className="text-sm font-medium text-foreground">Drag & drop files here</p>
          <p className="text-xs text-muted-foreground mt-1">PDF, JPEG, PNG — up to 25MB each</p>

          <div className="flex items-center justify-center gap-3 mt-4">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                setIsDirectoryMode(false);
                fileInputRef.current?.click();
              }}
            >
              <Upload className="h-3.5 w-3.5 mr-1.5" />
              Select Files
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                dirInputRef.current?.click();
              }}
            >
              <FolderOpen className="h-3.5 w-3.5 mr-1.5" />
              Select Folder
            </Button>
          </div>
        </div>

        {/* Hidden file inputs */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,image/jpeg,image/png"
          multiple
          className="hidden"
          onChange={() => {
            if (fileInputRef.current?.files?.length) {
              setIsDirectoryMode(false);
              addFiles(fileInputRef.current.files);
              fileInputRef.current.value = "";
            }
          }}
        />
        <input
          ref={dirInputRef}
          type="file"
          accept=".pdf,image/jpeg,image/png"
          multiple
          className="hidden"
          // @ts-expect-error webkitdirectory is non-standard but widely supported
          webkitdirectory=""
          onChange={() => {
            if (dirInputRef.current?.files?.length) {
              setIsDirectoryMode(true);
              addFiles(dirInputRef.current.files);
              dirInputRef.current.value = "";
            }
          }}
        />

        {/* Validation errors */}
        {errors.length > 0 && (
          <div className="space-y-1">
            {errors.map((err, i) => (
              <p key={i} className="text-xs text-red-600 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3 shrink-0" />
                {err}
              </p>
            ))}
            <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => setErrors([])}>
              Clear errors
            </Button>
          </div>
        )}

        {/* File list */}
        {files.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                {files.length} file{files.length !== 1 ? "s" : ""} selected
                {isDirectoryMode && " (directory)"}
              </p>
              <div className="flex items-center gap-2">
                {isDirectoryMode && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 text-xs"
                    onClick={() => {
                      setFiles([]);
                      setIsDirectoryMode(false);
                    }}
                  >
                    Cancel
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 text-xs"
                  onClick={() => setFiles([])}
                >
                  Clear all
                </Button>
              </div>
            </div>
            <div className="max-h-60 overflow-y-auto space-y-1">
              {files.map((f, i) => (
                <div
                  key={`${f.name}:${f.size}:${i}`}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted/50 text-xs"
                >
                  <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <span className="flex-1 truncate">{f.name}</span>
                  <span className="text-muted-foreground">{(f.size / 1024).toFixed(0)}KB</span>
                  <button
                    onClick={() => removeFile(i)}
                    className="text-muted-foreground hover:text-red-500 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>

            {isDirectoryMode ? (
              <Button
                className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                onClick={handleDirectoryCheck}
              >
                <FolderOpen className="h-4 w-4 mr-2" />
                Check & Extract ({files.length})
              </Button>
            ) : (
              <Button
                className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                onClick={handleExtract}
              >
                Extract All ({files.length})
              </Button>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── Checking Phase ──
  if (phase === "checking") {
    return (
      <div className="py-8 text-center space-y-4">
        <Loader2 className="h-10 w-10 animate-spin text-blue-500 mx-auto" />
        <div>
          <p className="text-sm font-medium">
            Checking {files.length} files against existing records...
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Finding files that already have records.
          </p>
        </div>
      </div>
    );
  }

  // ── Extracting Phase ──
  if (phase === "extracting") {
    return (
      <div className="py-8 text-center space-y-4">
        <Loader2 className="h-10 w-10 animate-spin text-blue-500 mx-auto" />
        <div>
          <p className="text-sm font-medium">Extracting data from {files.length} files...</p>
          <p className="text-xs text-muted-foreground mt-1">
            AI is analyzing each document. You can navigate away — results will be saved.
          </p>
        </div>
        <div className="max-w-xs mx-auto">
          <Progress value={extractProgress} className="h-2" />
          <p className="text-xs text-muted-foreground mt-1">{extractProgress}%</p>
        </div>
        <p className="text-xs text-muted-foreground">
          <ArrowRight className="h-3 w-3 inline mr-1" />
          You can browse other pages — a notification will appear when done.
        </p>
      </div>
    );
  }

  // ── Done Phase (directory mode) ──
  if (phase === "done" && isDirectoryMode) {
    return (
      <div className="space-y-4">
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-6">
            <CheckCircle2 className="h-6 w-6 text-emerald-600" />
            <p className="text-sm font-medium">
              {savedCount > 0
                ? `${savedCount} record${savedCount !== 1 ? "s" : ""} auto-saved with "To manually verify" tag`
                : "No new records to save"}
            </p>
            {errorCount > 0 && (
              <p className="text-xs text-red-600">
                {errorCount} file{errorCount !== 1 ? "s" : ""} had extraction errors
              </p>
            )}
            <Button size="sm" onClick={onComplete}>
              View Records
            </Button>
          </CardContent>
        </Card>

        {skippedFiles.length > 0 && (
          <details className="rounded-lg border border-blue-200 bg-blue-50/50 p-3">
            <summary className="text-xs font-medium text-blue-800 cursor-pointer">
              {skippedFiles.length} file{skippedFiles.length !== 1 ? "s" : ""} skipped (already have
              records)
            </summary>
            <ul className="mt-2 space-y-0.5 pl-4 list-disc text-xs text-blue-600">
              {skippedFiles.map((name, i) => (
                <li key={i}>{name}</li>
              ))}
            </ul>
          </details>
        )}

        {errorCount > 0 && (
          <details className="rounded-lg border border-red-200 bg-red-50/50 p-3">
            <summary className="text-xs font-medium text-red-800 cursor-pointer">
              {errorCount} file{errorCount !== 1 ? "s" : ""} with errors
            </summary>
            <ul className="mt-2 space-y-0.5 pl-4 list-disc text-xs text-red-600">
              {extractions
                .filter((e) => !!e.error)
                .map((item, i) => (
                  <li key={i}>
                    {item.filename}: {item.error}
                  </li>
                ))}
            </ul>
          </details>
        )}
      </div>
    );
  }

  // ── Review / Done Phase (normal batch mode) ──
  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3 text-sm">
          <span className="font-medium">
            {extractions.length} file{extractions.length !== 1 ? "s" : ""} extracted
          </span>
          {savedCount > 0 && (
            <Badge variant="secondary" className="bg-emerald-100 text-emerald-700 gap-1">
              <CheckCircle2 className="h-3 w-3" />
              {savedCount} saved
            </Badge>
          )}
          {skippedCount > 0 && (
            <Badge variant="secondary" className="gap-1">
              {skippedCount} skipped
            </Badge>
          )}
          {dupCount > 0 && (
            <Badge variant="secondary" className="bg-amber-100 text-amber-700 gap-1">
              <AlertTriangle className="h-3 w-3" />
              {dupCount} duplicate{dupCount !== 1 ? "s" : ""}
            </Badge>
          )}
          {errorCount > 0 && (
            <Badge variant="secondary" className="bg-red-100 text-red-700 gap-1">
              {errorCount} error{errorCount !== 1 ? "s" : ""}
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          {allDone && (
            <Button size="sm" onClick={onComplete}>
              <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
              View Records
            </Button>
          )}
        </div>
      </div>

      {/* Instruction */}
      <p className="text-xs text-muted-foreground">
        Review each extracted record below. Click a card to expand, edit if needed, then save. Use
        "Review Next" to step through cards one at a time.
      </p>

      {/* Guided review nav */}
      {pendingCount > 0 && !allDone && (
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant="outline"
            onClick={handleReviewNext}
            className="text-blue-600 border-blue-300 hover:bg-blue-50"
          >
            <FileText className="h-3.5 w-3.5 mr-1" />
            Review Next ({pendingCount} remaining)
          </Button>
          <span className="text-xs text-muted-foreground">
            {savedCount} of {extractions.length} saved
          </span>
        </div>
      )}

      {/* Card queue */}
      <div className="space-y-3">
        {extractions.map((item, i) => (
          <BatchRecordCard
            key={`${item.filename}:${i}`}
            index={i}
            item={item}
            memberId={memberId}
            onStatusChange={handleStatusChange}
            onDelete={handleDelete}
            defaultExpanded={activeIndex === i}
          />
        ))}
      </div>

      {/* Bottom action */}
      {allDone && (
        <Card>
          <CardContent className="flex items-center justify-center gap-3 py-6">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            <p className="text-sm font-medium">All records processed</p>
            <Button size="sm" onClick={onComplete}>
              Go to Records
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
