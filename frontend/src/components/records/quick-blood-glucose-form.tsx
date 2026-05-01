import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useQuickRecord } from "@/lib/quick-record";
import { ChevronDown, ChevronUp } from "lucide-react";

interface QuickBloodGlucoseFormProps {
  memberId: string;
  onSuccess: () => void;
  onCancel: () => void;
}

const INSULIN_TYPES = [
  { value: "rapid", label: "Rapid" },
  { value: "short", label: "Short" },
  { value: "intermediate", label: "Intermed." },
  { value: "long", label: "Long" },
  { value: "mixed", label: "Mixed" },
] as const;

export function QuickBloodGlucoseForm({
  memberId,
  onSuccess,
  onCancel,
}: QuickBloodGlucoseFormProps) {
  const [glucoseValue, setGlucoseValue] = useState("");
  const [mealTiming, setMealTiming] = useState<"before_food" | "after_food">("before_food");
  const [hba1cValue, setHba1cValue] = useState("");
  const [insulinDose, setInsulinDose] = useState("");
  const [insulinType, setInsulinType] = useState("");
  const [carbsConsumed, setCarbsConsumed] = useState("");
  const [notes, setNotes] = useState("");
  const [showExtra, setShowExtra] = useState(false);

  const { saving, error, setError, submit } = useQuickRecord({
    memberId,
    recordType: "blood_glucose",
    onSuccess,
  });

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const glucose = parseFloat(glucoseValue);
      const hba1c = parseFloat(hba1cValue);

      if (!glucose && !hba1c) {
        setError("Enter at least a glucose or HbA1c value");
        return;
      }
      if (glucose && (glucose < 20 || glucose > 600)) {
        setError("Enter a valid glucose value (20-600 mg/dL)");
        return;
      }
      if (hba1c && (hba1c < 2 || hba1c > 20)) {
        setError("Enter a valid HbA1c value (2-20%)");
        return;
      }

      const fields: Record<string, string> = {};
      if (glucose) {
        fields.glucose_value = glucoseValue;
        fields.meal_timing = mealTiming;
      }
      if (hba1c) fields.hba1c_value = hba1cValue;
      if (insulinDose) fields.insulin_dose = insulinDose;
      if (insulinType) fields.insulin_type = insulinType;
      if (carbsConsumed) fields.carbs_consumed = carbsConsumed;
      await submit(fields, notes || undefined);
    },
    [
      glucoseValue,
      mealTiming,
      hba1cValue,
      insulinDose,
      insulinType,
      carbsConsumed,
      notes,
      submit,
      setError,
    ]
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <p className="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">{error}</p>
      )}

      <div>
        <label className="text-sm font-medium block mb-1">Glucose (mg/dL)</label>
        <Input
          type="number"
          min="20"
          max="600"
          step="1"
          placeholder="e.g. 120"
          value={glucoseValue}
          onChange={(e) => setGlucoseValue(e.target.value)}
          autoFocus
        />
      </div>

      {glucoseValue && (
        <div>
          <label className="text-sm font-medium block mb-1">Meal Timing</label>
          <div className="flex gap-2">
            {(["before_food", "after_food"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setMealTiming(option)}
                className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                  mealTiming === option
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border hover:bg-muted/50"
                }`}
              >
                {option === "before_food" ? "Before Food" : "After Food"}
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <label className="text-sm font-medium block mb-1">HbA1c (%)</label>
        <Input
          type="number"
          min="2"
          max="20"
          step="0.1"
          placeholder="e.g. 6.5"
          value={hba1cValue}
          onChange={(e) => setHba1cValue(e.target.value)}
        />
      </div>

      {/* Expandable insulin/carbs section */}
      <button
        type="button"
        onClick={() => setShowExtra(!showExtra)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {showExtra ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        Insulin & Carbs
      </button>

      {showExtra && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium block mb-1">Insulin (units)</label>
              <Input
                type="number"
                min="0"
                max="100"
                step="0.5"
                placeholder="e.g. 10"
                value={insulinDose}
                onChange={(e) => setInsulinDose(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Carbs (g)</label>
              <Input
                type="number"
                min="0"
                max="500"
                step="1"
                placeholder="e.g. 45"
                value={carbsConsumed}
                onChange={(e) => setCarbsConsumed(e.target.value)}
              />
            </div>
          </div>

          {insulinDose && (
            <div>
              <label className="text-sm font-medium block mb-1">Insulin Type</label>
              <div className="flex flex-wrap gap-1.5">
                {INSULIN_TYPES.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => setInsulinType(t.value === insulinType ? "" : t.value)}
                    className={`rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      insulinType === t.value
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border hover:bg-muted/50"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div>
        <label className="text-sm font-medium block mb-1">Notes (optional)</label>
        <Input
          placeholder="Any notes..."
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      <div className="flex gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} className="flex-1">
          Cancel
        </Button>
        <Button type="submit" disabled={saving} className="flex-1">
          {saving ? "Saving..." : "Save"}
        </Button>
      </div>
    </form>
  );
}
