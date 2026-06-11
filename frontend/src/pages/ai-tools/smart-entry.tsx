import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AiToolsSubPage } from "@/components/ai-tools/ai-tools-layout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PenLine, Loader2, CheckCircle2 } from "lucide-react";
import { parseNaturalLanguage, createRecord } from "@/lib/api/records";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { RecordType } from "@/lib/types/enums";
import { toast } from "sonner";

export default function AiToolsSmartEntryPage() {
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";

  const [text, setText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState<{
    record_type: string | null;
    record_date: string | null;
    diagnosis: string | null;
    prescription_text: string | null;
    clinical_notes: string | null;
    confidence: string;
    preview_fields: { label: string; value: string }[];
  } | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleParse() {
    if (!text.trim()) return;
    setParsing(true);
    setParsed(null);
    try {
      const result = await parseNaturalLanguage(text);
      setParsed(result);
    } catch {
      toast.error("Failed to parse text");
    } finally {
      setParsing(false);
    }
  }

  async function handleSave() {
    if (!parsed || !parsed.record_date) return;
    setSaving(true);
    try {
      await createRecord(memberId, {
        record_type: (parsed.record_type || "misc_record") as RecordType,
        record_date: parsed.record_date,
        clinical_data: parsed.clinical_notes || "{}",
        diagnosis: parsed.diagnosis,
        prescription_text: parsed.prescription_text,
      });
      toast.success("Record created!");
      setText("");
      setParsed(null);
    } catch {
      toast.error("Failed to save record");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AiToolsSubPage title="Smart Entry">
      <div className="max-w-2xl space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <PenLine className="h-4 w-4" />
              Describe the Health Event
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              placeholder='e.g., "John had a fever of 102°F on January 15th. Dr. Smith prescribed paracetamol 500mg three times daily for 5 days. Diagnosis was viral fever."'
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              className="text-sm"
            />
            <Button onClick={handleParse} disabled={parsing || !text.trim()}>
              {parsing ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : null}
              Parse & Preview
            </Button>
          </CardContent>
        </Card>

        {/* Parsed result preview */}
        {parsed && (
          <Card className="border-blue-200 bg-blue-50/50">
            <CardContent className="pt-4 space-y-3">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">Confidence: {parsed.confidence}</Badge>
                {parsed.record_type && (
                  <Badge variant="secondary">
                    {RECORD_TYPE_LABELS[parsed.record_type as RecordType] || parsed.record_type}
                  </Badge>
                )}
              </div>

              {parsed.preview_fields.length > 0 && (
                <div className="space-y-1">
                  {parsed.preview_fields.map((field, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <span className="text-muted-foreground min-w-[120px]">{field.label}:</span>
                      <span className="font-medium">{field.value}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-2 pt-2">
                <Button
                  onClick={handleSave}
                  disabled={saving || !parsed.record_date}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  {saving ? (
                    <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
                  )}
                  {saving ? "Saving..." : "Save as Record"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AiToolsSubPage>
  );
}
