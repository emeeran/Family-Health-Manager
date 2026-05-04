import { API_BASE_URL } from "../constants";

async function downloadCSV(path: string, filename: string) {
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, { credentials: "include" });

  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!response.ok) {
    throw new Error(`Export failed: ${response.statusText}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(objectUrl);
}

export function exportRecords(memberId?: string, recordType?: string) {
  const params = new URLSearchParams();
  if (memberId) params.set("member_id", memberId);
  if (recordType) params.set("record_type", recordType);
  const qs = params.toString();
  return downloadCSV(`/export/records${qs ? `?${qs}` : ""}`, "health-records.csv");
}

export function exportMedications(memberId?: string) {
  const params = new URLSearchParams();
  if (memberId) params.set("member_id", memberId);
  const qs = params.toString();
  return downloadCSV(`/export/medications${qs ? `?${qs}` : ""}`, "medications.csv");
}

export function exportLabResults(memberId?: string) {
  const params = new URLSearchParams();
  if (memberId) params.set("member_id", memberId);
  const qs = params.toString();
  return downloadCSV(`/export/lab-results${qs ? `?${qs}` : ""}`, "lab-results.csv");
}
