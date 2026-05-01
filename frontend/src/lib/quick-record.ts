import { useState, useCallback } from "react";
import { createRecord } from "@/lib/api/records";
import { serializeClinicalData } from "@/lib/clinical-data";
import { ApiError } from "@/lib/api-client";
import { toast } from "sonner";
import type { RecordType } from "./types/enums";

/** Get today's date as YYYY-MM-DD */
export function todayISO(): string {
  return new Date().toISOString().split("T")[0];
}

/** Get current time as HH:MM */
export function nowTime(): string {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

interface UseQuickRecordOptions {
  memberId: string;
  recordType: RecordType;
  /** Toast message on success (default: "Recorded") */
  successMessage?: string;
  onSuccess: () => void;
}

/**
 * Shared hook for quick-entry form submission.
 * Handles token check, clinical data serialization, record creation, toast, and error state.
 */
export function useQuickRecord({
  memberId,
  recordType,
  successMessage = "Recorded",
  onSuccess,
}: UseQuickRecordOptions) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = useCallback(
    async (fields: Record<string, string>, notes?: string) => {
      setError("");
      setSaving(true);
      try {
        const clinicalData = serializeClinicalData(recordType, fields, {}, notes || undefined);

        await createRecord(memberId, {
          record_type: recordType,
          record_date: todayISO(),
          record_time: nowTime(),
          clinical_data: clinicalData,
          diagnosis: null,
          prescription_text: null,
          provider_id: null,
          next_review_date: null,
          tags: null,
        });

        toast.success(successMessage);
        onSuccess();
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          toast.info("Already recorded");
          onSuccess();
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to save");
      } finally {
        setSaving(false);
      }
    },
    [recordType, memberId, successMessage, onSuccess]
  );

  return { saving, error, setError, submit };
}
