import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useQuickRecord } from "@/lib/quick-record";

interface QuickVitalsFormProps {
  memberId: string;
  onSuccess: () => void;
  onCancel: () => void;
}

export function QuickVitalsForm({ memberId, onSuccess, onCancel }: QuickVitalsFormProps) {
  const [weight, setWeight] = useState("");
  const [bp, setBp] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [temperature, setTemperature] = useState("");
  const [notes, setNotes] = useState("");

  const { saving, error, setError, submit } = useQuickRecord({
    memberId,
    recordType: "vitals",
    successMessage: "Vitals recorded",
    onSuccess,
  });

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!weight && !bp && !heartRate && !temperature) {
        setError("Enter at least one vital sign");
        return;
      }
      const fields: Record<string, string> = {};
      if (weight) fields.weight = weight;
      if (bp) fields.blood_pressure = bp;
      if (heartRate) fields.heart_rate = heartRate;
      if (temperature) fields.temperature = temperature;
      await submit(fields, notes || undefined);
    },
    [weight, bp, heartRate, temperature, notes, submit, setError]
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <p className="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">{error}</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-sm font-medium block mb-1">Weight (kg)</label>
          <Input
            type="number"
            min="1"
            max="500"
            step="0.1"
            placeholder="e.g. 72.5"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label className="text-sm font-medium block mb-1">BP (mmHg)</label>
          <Input placeholder="e.g. 120/80" value={bp} onChange={(e) => setBp(e.target.value)} />
        </div>
        <div>
          <label className="text-sm font-medium block mb-1">Heart Rate (bpm)</label>
          <Input
            type="number"
            min="30"
            max="250"
            step="1"
            placeholder="e.g. 72"
            value={heartRate}
            onChange={(e) => setHeartRate(e.target.value)}
          />
        </div>
        <div>
          <label className="text-sm font-medium block mb-1">Temp (°F)</label>
          <Input
            type="number"
            min="90"
            max="115"
            step="0.1"
            placeholder="e.g. 98.6"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
          />
        </div>
      </div>

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
