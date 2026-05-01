import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useQuickRecord } from "@/lib/quick-record";

interface QuickParkinsonsFormProps {
  memberId: string;
  onSuccess: () => void;
  onCancel: () => void;
}

const MOTOR_STATES = [
  {
    value: "on",
    label: "ON",
    desc: "Good mobility",
    color: "border-emerald-400 bg-emerald-50 text-emerald-700",
  },
  {
    value: "off",
    label: "OFF",
    desc: "Reduced mobility",
    color: "border-red-400 bg-red-50 text-red-700",
  },
  {
    value: "wearing_off",
    label: "Wearing Off",
    desc: "Med fading",
    color: "border-amber-400 bg-amber-50 text-amber-700",
  },
  {
    value: "dyskinesia",
    label: "Dyskinesia",
    desc: "Involuntary mvmt",
    color: "border-purple-400 bg-purple-50 text-purple-700",
  },
] as const;

const SEVERITY_LEVELS = [
  { value: "none", label: "None" },
  { value: "mild", label: "Mild" },
  { value: "moderate", label: "Moderate" },
  { value: "severe", label: "Severe" },
];

export function QuickParkinsonsForm({ memberId, onSuccess, onCancel }: QuickParkinsonsFormProps) {
  const [motorState, setMotorState] = useState("");
  const [tremor, setTremor] = useState("");
  const [rigidity, setRigidity] = useState("");
  const [bradykinesia, setBradykinesia] = useState("");
  const [gait, setGait] = useState("");
  const [mood, setMood] = useState("");
  const [sleep, setSleep] = useState("");
  const [notes, setNotes] = useState("");

  const { saving, error, setError, submit } = useQuickRecord({
    memberId,
    recordType: "parkinsons_log",
    successMessage: "PD log recorded",
    onSuccess,
  });

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!motorState) {
        setError("Select a motor state");
        return;
      }
      const fields: Record<string, string> = { motor_state: motorState };
      if (tremor) fields.tremor_severity = tremor;
      if (rigidity) fields.rigidity = rigidity;
      if (bradykinesia) fields.bradykinesia = bradykinesia;
      if (gait) fields.gait_balance = gait;
      if (mood) fields.mood = mood;
      if (sleep) fields.sleep_quality = sleep;
      await submit(fields, notes || undefined);
    },
    [motorState, tremor, rigidity, bradykinesia, gait, mood, sleep, notes, submit, setError]
  );

  function SeveritySelect({
    label,
    value,
    onChange,
  }: {
    label: string;
    value: string;
    onChange: (v: string) => void;
  }) {
    return (
      <div>
        <label className="text-xs font-medium block mb-1">{label}</label>
        <div className="flex gap-1">
          {SEVERITY_LEVELS.map((l) => (
            <button
              key={l.value}
              type="button"
              onClick={() => onChange(l.value === value ? "" : l.value)}
              className={`flex-1 rounded border px-1.5 py-1.5 text-[11px] font-medium transition-colors ${
                value === l.value
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:bg-muted/50 text-muted-foreground"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <p className="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">{error}</p>
      )}

      {/* Motor State */}
      <div>
        <label className="text-sm font-medium block mb-1.5">Motor State</label>
        <div className="grid grid-cols-2 gap-2">
          {MOTOR_STATES.map((ms) => (
            <button
              key={ms.value}
              type="button"
              onClick={() => setMotorState(ms.value)}
              className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                motorState === ms.value ? ms.color : "border-border hover:bg-muted/50"
              }`}
            >
              <span className="text-sm font-bold block">{ms.label}</span>
              <span className="text-[10px] opacity-70">{ms.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Symptoms */}
      <div className="space-y-2">
        <SeveritySelect label="Tremor" value={tremor} onChange={setTremor} />
        <SeveritySelect label="Rigidity" value={rigidity} onChange={setRigidity} />
        <SeveritySelect label="Slowness" value={bradykinesia} onChange={setBradykinesia} />
        <SeveritySelect label="Gait" value={gait} onChange={setGait} />
      </div>

      {/* Mood & Sleep */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs font-medium block mb-1">Mood</label>
          <div className="flex flex-wrap gap-1">
            {(["good", "fair", "low", "anxious"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMood(m === mood ? "" : m)}
                className={`rounded border px-2 py-1 text-[11px] font-medium transition-colors ${
                  mood === m
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border hover:bg-muted/50 text-muted-foreground"
                }`}
              >
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs font-medium block mb-1">Sleep</label>
          <div className="flex flex-wrap gap-1">
            {(["good", "fair", "poor", "insomnia"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSleep(s === sleep ? "" : s)}
                className={`rounded border px-2 py-1 text-[11px] font-medium transition-colors ${
                  sleep === s
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border hover:bg-muted/50 text-muted-foreground"
                }`}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div>
        <label className="text-sm font-medium block mb-1">Notes</label>
        <Input
          placeholder="Any observations..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      <div className="flex gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} className="flex-1">
          Cancel
        </Button>
        <Button type="submit" disabled={saving} className="flex-1">
          {saving ? "Saving..." : "Log"}
        </Button>
      </div>
    </form>
  );
}
