import { useState, useEffect, memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { VerificationBadge } from "@/components/shared/verification-badge";
import { streamRequest, ApiError } from "@/lib/api-client";
import { listProviders } from "@/lib/api/providers";
import {
  ClipboardList,
  Sparkles,
  Loader2,
  CheckCircle2,
  Stethoscope,
  UserRound,
  FilePlus2,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import type { GeneratedInsight } from "@/lib/api/members";

import type { ProviderResponse } from "@/lib/types/provider";

export interface PreConsultationCardProps {
  memberId: string;
  memberFirstName: string;
  onNoteReady: (note: GeneratedInsight) => void;
  onViewNote: () => void;
  existingNote: GeneratedInsight | null;
}

export const PreConsultationCard = memo(function PreConsultationCard({
  memberId,
  memberFirstName: _memberFirstName,
  onNoteReady,
  onViewNote,
  existingNote,
}: PreConsultationCardProps) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState<GeneratedInsight | null>(existingNote);
  const [streamText, setStreamText] = useState("");
  const [streamStage, setStreamStage] = useState("");
  const [symptoms, setSymptoms] = useState("");
  const [showSymptomInput, setShowSymptomInput] = useState(!existingNote);
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string>("");

  useEffect(() => {
    if (existingNote && showSymptomInput) {
      setShowSymptomInput(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingNote]);

  // Fetch providers for this member
  useEffect(() => {
    listProviders()
      .then((all) => {
        // Filter to providers assigned to this member
        const memberProviders = all.filter((p) =>
          p.assigned_members.some((m) => m.family_member_id === memberId)
        );
        setProviders(memberProviders);
      })
      .catch(() => {});
  }, [memberId]);

  async function handleGenerate() {
    setLoading(true);
    setStreamText("");
    setStreamStage("Loading medical history...");
    try {
      let fullText = "";
      const params = new URLSearchParams();
      if (symptoms.trim()) params.set("symptoms", symptoms.trim());
      if (selectedProviderId) params.set("provider_id", selectedProviderId);
      const qs = params.toString() ? `?${params.toString()}` : "";
      await streamRequest(`/members/${memberId}/pre-consultation-note/stream${qs}`, {
        onEvent: (event) => {
          const e = event as Record<string, unknown>;
          const stage = e.stage as string;
          if (stage === "context") {
            setStreamStage((e.message as string) || "Preparing...");
          } else if (stage === "provider") {
            setStreamStage(`Generating via ${e.provider}...`);
          } else if (stage === "token") {
            fullText += e.content as string;
            setStreamText(fullText);
          } else if (stage === "complete") {
            const result: GeneratedInsight = {
              id: e.insight_id as string,
              response: fullText,
              provider_used: e.provider as string,
              generated_at: new Date().toISOString(),
              verification: null,
            };
            setNote(result);
            setStreamStage("");
            setShowSymptomInput(false);
            onNoteReady(result);
          } else if (stage === "error") {
            toast.error((e.message as string) || "Generation failed");
          }
        },
      });
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = err.data?.message || err.data?.error || err.message || "Unknown";
        console.error("Pre-consult API error:", err.status, err.data);
        toast.error(`Failed to generate: ${detail} (${err.status})`);
      } else {
        console.error("Pre-consult error:", err);
        toast.error(`Failed to generate: ${err instanceof Error ? err.message : "Unknown error"}`);
      }
    } finally {
      setLoading(false);
      setStreamStage("");
    }
  }

  const currentNote = note || existingNote;
  const selectedProvider = providers.find((p) => p.id === selectedProviderId);

  // Streaming state
  if (loading) {
    return (
      <Card className="overflow-hidden">
        <div className="h-1.5 bg-gradient-to-r from-teal-500 to-cyan-500" />
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Stethoscope className="h-5 w-5 text-teal-600" />
            Preparing Your Visit Note
            {selectedProvider && (
              <span className="text-xs font-normal text-muted-foreground">
                for {selectedProvider.name}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {streamText ? (
            <div className="p-3 rounded-lg bg-muted/30">
              {streamStage && (
                <p className="text-xs text-teal-600 font-medium mb-2">{streamStage}</p>
              )}
              <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
                {streamText}
                <span className="inline-block w-1.5 h-4 bg-teal-500 animate-pulse ml-0.5 align-text-bottom" />
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/30">
              <Loader2 className="h-5 w-5 animate-spin text-teal-500" />
              <p className="text-sm text-foreground/70 font-medium">
                {streamStage || "Analyzing medical history..."}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  // Completed state — show note summary
  if (currentNote && !showSymptomInput) {
    return (
      <Card className="overflow-hidden">
        <div className="h-1.5 bg-gradient-to-r from-teal-500 to-cyan-500" />
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <ClipboardList className="h-5 w-5 text-teal-600" />
            Pre-Consultation Note
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-50 border border-emerald-200">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            <p className="text-sm text-emerald-800 flex-1">
              Note prepared{" "}
              {new Date(currentNote.generated_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}{" "}
              via <span className="font-bold">{currentNote.provider_used}</span>
            </p>
            <VerificationBadge verification={currentNote.verification} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const params = new URLSearchParams({ type: "doctor_visit" });
                if (symptoms.trim()) params.set("chief_complaint", symptoms.trim());
                if (selectedProviderId) params.set("provider_id", selectedProviderId);
                navigate(`/members/${memberId}/records/new?${params.toString()}`);
              }}
            >
              <FilePlus2 className="h-3.5 w-3.5 mr-1" />
              Create Record
            </Button>
            <Button size="sm" variant="outline" onClick={onViewNote}>
              View Note
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowSymptomInput(true)}>
              <Sparkles className="h-3.5 w-3.5 mr-1" />
              Regenerate
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Input state — ask for doctor, symptoms, then generate
  return (
    <Card className="overflow-hidden">
      <div className="h-1.5 bg-gradient-to-r from-teal-500 to-cyan-500" />
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Stethoscope className="h-5 w-5 text-teal-600" />
          Pre-Consultation Note
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-foreground/70">
          Select which doctor you're visiting and describe your symptoms. The AI will generate
          cryptic, specialty-focused questions you can ask during the visit.
        </p>

        {/* Provider selector */}
        {providers.length > 0 && (
          <div className="space-y-1.5">
            <Label className="text-xs font-medium flex items-center gap-1.5">
              <UserRound className="h-3.5 w-3.5" />
              Consulting Doctor
            </Label>
            <Select
              value={selectedProviderId}
              onValueChange={(v) => setSelectedProviderId(v === "__none__" ? "" : (v ?? ""))}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a doctor (optional)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">General visit (no specific doctor)</SelectItem>
                {providers.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                    {p.speciality ? ` — ${p.speciality}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedProvider?.speciality && (
              <p className="text-xs text-teal-600 font-medium">
                Questions will be {selectedProvider.speciality}-specific and cryptic
              </p>
            )}
          </div>
        )}

        <Textarea
          placeholder={`E.g.:\n- Frequent headaches for the past 2 weeks\n- Feeling tired and dizzy\n- Blood sugar readings have been high`}
          rows={4}
          value={symptoms}
          onChange={(e) => setSymptoms(e.target.value)}
          className="text-sm"
          disabled={loading}
        />

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={handleGenerate}
            disabled={loading}
            className="bg-gradient-to-r from-teal-500 to-cyan-500 text-white hover:from-teal-600 hover:to-cyan-600"
          >
            <Sparkles className="h-4 w-4 mr-1.5" />
            Generate Visit Note
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={handleGenerate}
            disabled={loading}
            className="text-xs text-muted-foreground"
          >
            Generate without symptoms
          </Button>
        </div>
      </CardContent>
    </Card>
  );
});
