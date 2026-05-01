"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createRecord } from "@/lib/api/records";
import { serializeClinicalData } from "@/lib/clinical-data";
import { todayISO, nowTime } from "@/lib/quick-record";
import { ApiError } from "@/lib/api-client";
import { toast } from "sonner";
import type { RecordType } from "@/lib/types/enums";

interface ParsedCommand {
  type: RecordType;
  fields: Record<string, string>;
  notes?: string;
}

/**
 * Parse natural language health input into a structured record.
 * Examples:
 *   "blood sugar 120 before food"
 *   "sugar 95 after lunch"
 *   "weight 72kg bp 120/80 heart rate 72"
 *   "glucose 140 pp"
 *   "bp 130/85"
 *   "temperature 98.6"
 */
function parseHealthInput(text: string): ParsedCommand | null {
  const lower = text.toLowerCase().trim();
  if (!lower) return null;

  // Blood glucose patterns
  const glucoseMatch = lower.match(
    /(?:blood\s*sugar|sugar|glucose|fbs|ppbs|rbs|pp)\s*[:\s]*\s*(\d+(?:\.\d+)?)/
  );
  if (glucoseMatch) {
    const value = glucoseMatch[1];
    let mealTiming = "before_food";
    if (
      /after|pp|post\s*prandial|lunch|dinner|breakfast.*after|after.*food/.test(
        lower.replace(glucoseMatch[0], "")
      )
    ) {
      mealTiming = "after_food";
    }
    if (/\bfbs\b|fasting/.test(lower)) mealTiming = "before_food";
    if (/\bpp\b|ppbs/.test(lower)) mealTiming = "after_food";

    return {
      type: "blood_glucose",
      fields: { glucose_value: value, meal_timing: mealTiming },
      notes: lower.includes("note") ? text.split(/note/i).pop()?.trim() : undefined,
    };
  }

  // Vitals patterns — weight, bp, heart rate, temperature
  const vitalsFields: Record<string, string> = {};
  let hasVital = false;

  const weightMatch = lower.match(/weight\s*[:\s]*\s*(\d+(?:\.\d+)?)/);
  if (weightMatch) {
    vitalsFields.weight = weightMatch[1];
    hasVital = true;
  }

  const bpMatch = lower.match(/bp\s*[:\s]*\s*(\d+)\s*\/\s*(\d+)/);
  if (bpMatch) {
    vitalsFields.blood_pressure = `${bpMatch[1]}/${bpMatch[2]}`;
    hasVital = true;
  }

  const hrMatch = lower.match(/(?:heart\s*rate|pulse|hr)\s*[:\s]*\s*(\d+)/);
  if (hrMatch) {
    vitalsFields.heart_rate = hrMatch[1];
    hasVital = true;
  }

  const tempMatch = lower.match(/(?:temp|temperature|fever)\s*[:\s]*\s*(\d+(?:\.\d+)?)/);
  if (tempMatch) {
    vitalsFields.temperature = tempMatch[1];
    hasVital = true;
  }

  if (hasVital) {
    return {
      type: "vitals",
      fields: vitalsFields,
      notes: lower.includes("note") ? text.split(/note/i).pop()?.trim() : undefined,
    };
  }

  return null;
}

interface QuickLogInputProps {
  memberId: string;
  memberName?: string;
  onLogged?: () => void;
}

export function QuickLogInput({ memberId, memberName, onLogged }: QuickLogInputProps) {
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<ParsedCommand | null>(null);
  const [error, setError] = useState("");

  const handleInputChange = useCallback((value: string) => {
    setInput(value);
    setError("");
    if (value.trim()) {
      const parsed = parseHealthInput(value);
      setPreview(parsed);
    } else {
      setPreview(null);
    }
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const parsed = parseHealthInput(input);
      if (!parsed) {
        setError(
          'Couldn\'t understand that. Try: "blood sugar 120 before food" or "weight 72kg bp 120/80"'
        );
        return;
      }

      setSaving(true);
      try {
        const clinicalData = serializeClinicalData(parsed.type, parsed.fields, {}, parsed.notes);

        await createRecord(memberId, {
          record_type: parsed.type,
          record_date: todayISO(),
          record_time: nowTime(),
          clinical_data: clinicalData,
          diagnosis: null,
          prescription_text: null,
          provider_id: null,
          next_review_date: null,
          tags: null,
        });

        toast.success(
          parsed.type === "blood_glucose"
            ? `Glucose ${parsed.fields.glucose_value} mg/dL logged`
            : "Vitals logged"
        );
        setInput("");
        setPreview(null);
        onLogged?.();
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          toast.info("Already logged");
          setInput("");
          setPreview(null);
          onLogged?.();
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to save");
      } finally {
        setSaving(false);
      }
    },
    [input, memberId, onLogged]
  );

  const typeLabel =
    preview?.type === "blood_glucose"
      ? "Blood Glucose"
      : preview?.type === "vitals"
        ? "Vitals"
        : null;

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex gap-2">
        <Input
          placeholder='Quick log: "blood sugar 120 before food" or "weight 72kg bp 120/80"'
          value={input}
          onChange={(e) => handleInputChange(e.target.value)}
          className="flex-1 text-sm"
          disabled={saving}
        />
        <Button type="submit" size="sm" disabled={saving || !input.trim()}>
          {saving ? "..." : "Log"}
        </Button>
      </div>
      {preview && (
        <p className="text-xs text-muted-foreground">
          {memberName ? `${memberName} · ` : ""}
          <span className="font-medium text-foreground">{typeLabel}</span>
          {" — "}
          {Object.entries(preview.fields)
            .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
            .join(", ")}
        </p>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </form>
  );
}
