import type { HealthRecordResponse } from "./types/health-record";

export function extractReason(record: HealthRecordResponse): string {
  if (record.diagnosis) return record.diagnosis;
  try {
    const parsed = JSON.parse(record.clinical_data);
    if (parsed._type === "structured" && parsed.chief_complaint) return parsed.chief_complaint;
  } catch {
    /* fall through */
  }
  return "";
}

export function extractSummary(record: HealthRecordResponse): string | null {
  try {
    const parsed = JSON.parse(record.clinical_data);
    if (parsed._type !== "structured") return null;
    const parts: string[] = [];

    const rxs = parsed.prescriptions as Record<string, string>[] | undefined;
    if (rxs?.length) {
      const names = rxs.map((r) => r.medicine).filter(Boolean);
      if (names.length)
        parts.push(
          `Rx: ${names.slice(0, 3).join(", ")}${names.length > 3 ? ` +${names.length - 3}` : ""}`
        );
    }

    const labs = parsed.lab_results || (parsed.tests as Record<string, string>[] | undefined);
    if (Array.isArray(labs) && labs.length) {
      const highlights = labs.slice(0, 3).map((t: Record<string, string>) => {
        const name = t.test_name || "";
        const result = t.result || "";
        const flag = t.flag || t.status || "";
        return flag === "High" || flag === "Low" || flag === "Abnormal"
          ? `${name}: ${result} ↑`
          : `${name}: ${result}`;
      });
      if (highlights.length) parts.push(highlights.join(" · "));
    }

    if (parsed.glucose_value)
      parts.push(`Glucose: ${parsed.glucose_value} mg/dL (${parsed.meal_timing || ""})`);

    if (parsed.hba1c_value) parts.push(`HbA1c: ${parsed.hba1c_value}%`);

    if (parsed.eyeglass) {
      const e = parsed.eyeglass as Record<string, string>;
      if (e.sph_right || e.sph_left) parts.push(`SPH: ${e.sph_right || ""} / ${e.sph_left || ""}`);
    }

    if (parsed.bp) parts.push(`BP: ${parsed.bp}`);
    if (parsed.pulse) parts.push(`Pulse: ${parsed.pulse}`);
    if (parsed.temperature) parts.push(`Temp: ${parsed.temperature}`);

    return parts.length > 0 ? parts.join("  |  ") : null;
  } catch {
    return null;
  }
}

export function extractParkinsonsSummary(record: HealthRecordResponse): string | null {
  try {
    const parsed = JSON.parse(record.clinical_data);
    if (parsed._type !== "structured" || parsed._recordType !== "parkinsons_log") return null;
    const parts: string[] = [];
    const motorLabels: Record<string, string> = {
      on: "ON",
      off: "OFF",
      wearing_off: "Wearing Off",
      dyskinesia: "Dyskinesia",
    };
    if (parsed.motor_state) parts.push(motorLabels[parsed.motor_state] || parsed.motor_state);
    const symptoms: string[] = [];
    if (parsed.tremor_severity && parsed.tremor_severity !== "none")
      symptoms.push(`Tremor: ${parsed.tremor_severity}`);
    if (parsed.rigidity && parsed.rigidity !== "none") symptoms.push(`Rigid: ${parsed.rigidity}`);
    if (parsed.bradykinesia && parsed.bradykinesia !== "none")
      symptoms.push(`Slow: ${parsed.bradykinesia}`);
    if (parsed.gait_balance && parsed.gait_balance !== "normal")
      symptoms.push(`Gait: ${parsed.gait_balance}`);
    if (symptoms.length) parts.push(symptoms.join(" · "));
    return parts.length > 0 ? parts.join("  |  ") : null;
  } catch {
    return null;
  }
}
