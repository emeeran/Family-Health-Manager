import { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, Activity, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MemberPicker } from "@/components/shared/member-picker";
import { setPendingEntry } from "@/lib/pending-entry";
import { toast } from "sonner";

/**
 * SmartEntryBar — a thin launcher.
 *
 * Previously this reimplemented NL parsing, document extraction, a review dialog,
 * record creation, and medication sync. All of that now lives in the record wizard
 * (which has first-class NL + upload + medication-sync). The bar just collects a
 * member + text/file and routes into the wizard, so there is a single AI entry path.
 */
interface SmartEntryBarProps {
  members: { id: string; first_name: string; last_name: string; is_active: boolean }[];
}

export function SmartEntryBar({ members }: SmartEntryBarProps) {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState("");
  const [selectedMemberId, setSelectedMemberId] = useState("");

  const activeMembers = members.filter((m) => m.is_active);

  // Default to the first active member so the launcher always has a target.
  useEffect(() => {
    if (!selectedMemberId && activeMembers[0]) {
      setSelectedMemberId(activeMembers[0].id);
    }
  }, [activeMembers, selectedMemberId]);

  const launch = useCallback(
    (memberId: string, nlText?: string, file?: File) => {
      if (file) setPendingEntry({ file });
      const search = nlText ? `?nl=${encodeURIComponent(nlText)}` : "";
      navigate(`/people/${memberId}/records/new${search}`);
    },
    [navigate]
  );

  const handleParse = useCallback(() => {
    const text = input.trim();
    if (!text) return;
    const memberId = selectedMemberId || activeMembers[0]?.id;
    if (!memberId) {
      toast.error("Please select a family member first");
      return;
    }
    launch(memberId, text);
  }, [input, selectedMemberId, activeMembers, launch]);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const memberId = selectedMemberId || activeMembers[0]?.id;
      if (!memberId) {
        toast.error("Please select a family member first");
        return;
      }
      e.target.value = ""; // allow re-picking the same file later
      launch(memberId, undefined, file);
    },
    [selectedMemberId, activeMembers, launch]
  );

  return (
    <div className="flex items-center gap-2 rounded-xl border shadow-sm bg-card p-2">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--brand-accent)]/10 text-[var(--brand-accent)]">
        <Activity className="h-4 w-4" />
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleParse();
        }}
        className="flex flex-1 items-center gap-2"
      >
        <Input
          placeholder='Describe: "dad visited doctor, prescribed metformin 500mg" or "blood sugar 120"'
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 h-9 text-sm focus-visible:ring-[var(--brand-accent)]/30"
        />
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.pdf"
          className="hidden"
          onChange={handleFileChange}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 gap-1.5 shrink-0"
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Upload</span>
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={!input.trim()}
          className="h-9 shrink-0 gap-1.5 bg-[var(--brand-accent)] text-white hover:bg-[var(--brand-accent)]/90"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Smart Entry</span>
          <span className="sm:hidden">Add</span>
        </Button>
      </form>
      <MemberPicker
        members={members}
        value={selectedMemberId}
        onChange={setSelectedMemberId}
        size="sm"
      />
    </div>
  );
}
