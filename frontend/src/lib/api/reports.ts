import { API_BASE_URL } from "../constants";

export async function downloadHealthSummary(memberId?: string) {
  const params = new URLSearchParams();
  if (memberId) params.set("member_id", memberId);
  const qs = params.toString();
  const url = `${API_BASE_URL}/reports/health-summary${qs ? `?${qs}` : ""}`;

  const response = await fetch(url, { credentials: "include" });

  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!response.ok) {
    throw new Error(`Report generation failed: ${response.statusText}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = "health-summary.pdf";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(objectUrl);
}
