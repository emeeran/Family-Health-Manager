import { memo, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, Activity, FlaskConical, Users, Plus, Phone, Printer, Bell } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { HealthScoreRing, scoreTextColor } from "@/components/ui/health-score-ring";
import { ActiveMedicationsTable } from "@/components/members/active-medications-table";
import { GENDER_LABELS, RELATIONSHIP_LABELS, HBA1C_CATEGORY_COLORS } from "@/lib/constants";
import { deleteMember } from "@/lib/api/members";
import { formatDate, formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";
import type { MemberDetailResponse } from "@/lib/types/member";
import { useState } from "react";

/* ── Helpers ── */

function getHba1cCategory(value: number): string {
  if (value < 5.7) return "Normal";
  if (value < 6.5) return "Prediabetes";
  return "Diabetes";
}

const quickActions = [
  {
    label: "Record",
    icon: Plus,
    hrefSuffix: "/records/new",
    color: "text-blue-600 hover:bg-blue-50",
  },
  {
    label: "Records",
    icon: FileText,
    hrefSuffix: "/records",
    color: "text-teal-600 hover:bg-teal-50",
  },
  {
    label: "Timeline",
    icon: Activity,
    hrefSuffix: "/timeline",
    color: "text-amber-600 hover:bg-amber-50",
  },
  {
    label: "Labs",
    icon: FlaskConical,
    hrefSuffix: "/lab-records",
    color: "text-emerald-600 hover:bg-emerald-50",
  },
  {
    label: "Providers",
    icon: Users,
    hrefSuffix: "/providers",
    color: "text-violet-600 hover:bg-violet-50",
  },
];

interface OverviewTabProps {
  data: MemberDetailResponse;
}

export const OverviewTab = memo(function OverviewTab({ data }: OverviewTabProps) {
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const {
    member,
    brief_medical_history,
    active_medications,
    active_conditions_count,
    active_medications_count,
    age,
    health_score,
    score_breakdown,
    provider_assignments,
    risk_assessment,
    hba1c_history,
    drug_interactions,
    recent_records,
    upcoming_reminders,
  } = data;

  const memberName = `${member.first_name} ${member.last_name}`;
  const hasAllergies = member.allergies && member.allergies.length > 0;
  const hasEmergency = member.emergency_contact_name || member.emergency_contact_phone;

  const recordsThisMonth = useMemo(() => {
    const now = new Date();
    const thisMonth = now.getFullYear() * 12 + now.getMonth();
    return recent_records.filter(
      (r) =>
        r.record_date &&
        new Date(r.record_date).getFullYear() * 12 + new Date(r.record_date).getMonth() ===
          thisMonth
    ).length;
  }, [recent_records]);

  const lastRecordDate = useMemo(() => {
    if (recent_records.length === 0) return null;
    return recent_records[0].record_date;
  }, [recent_records]);

  const medHistoryTags = useMemo(() => {
    if (!brief_medical_history)
      return { conditions: [] as string[], allergies: [] as string[], surgeries: [] as string[] };
    const parts = brief_medical_history.split("; ").reduce((acc: Record<string, string>, part) => {
      const idx = part.indexOf(":");
      if (idx > 0) acc[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
      return acc;
    }, {});
    return {
      conditions: (parts["Conditions"] || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      allergies: (parts["Allergies"] || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      surgeries: (parts["Surgeries"] || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
  }, [brief_medical_history]);

  const riskLevel = risk_assessment?.level;
  const riskDot =
    riskLevel === "high"
      ? "bg-red-500"
      : riskLevel === "moderate"
        ? "bg-amber-500"
        : riskLevel === "low"
          ? "bg-emerald-500"
          : null;

  async function handleDelete() {
    try {
      await deleteMember(member.id);
      toast.success("Member deleted");
      navigate("/members");
    } catch {
      toast.error("Failed to delete member");
    }
  }

  function handleExportPDF() {
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const mn = `${member.first_name} ${member.last_name}`;
    const now = new Date().toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
    const time = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    const meds = active_medications ?? [];
    const tc = "border:1px solid #CCCCCC;padding:4px 6px;font-size:10px;";
    const thc = tc + "background:#F5F5F5;font-weight:bold;font-size:9px;text-align:left;";

    const histParts: string[] = [];
    if (brief_medical_history) {
      const rawParts = brief_medical_history
        .split(";")
        .map((s: string) => s.trim())
        .filter(Boolean);
      for (const part of rawParts) {
        const colonIdx = part.indexOf(":");
        if (colonIdx > 0) {
          const label = part.slice(0, colonIdx).trim();
          const items = part.slice(colonIdx + 1).trim();
          histParts.push(`<span style="font-weight:600">${esc(label)}:</span> ${esc(items)}`);
        } else {
          histParts.push(esc(part));
        }
      }
    }

    const medRows = meds
      .map((m) => {
        const dose = m.dosage || "--";
        const t = m.timing ? m.timing.replace(/_/g, " ") : "--";
        const prov = m.provider_name || "--";
        const date = m.prescribed_date
          ? new Date(m.prescribed_date).toLocaleDateString("en-GB", {
              day: "2-digit",
              month: "short",
              year: "numeric",
            })
          : "--";
        return `<tr><td style="${tc}">${esc(m.type || "--")}</td><td style="${tc};font-weight:600">${esc(m.medicine)}</td><td style="${tc};white-space:nowrap">${esc(dose)}</td><td style="${tc}">${esc(t)}</td><td style="${tc}">${esc(prov)}</td><td style="${tc};white-space:nowrap">${date}</td></tr>`;
      })
      .join("");

    const html = `<!DOCTYPE html><html><head><title>${esc(mn)} — Health Profile</title>
<style>
  @page { margin: 0.75in 1in; }
  * { margin: 0; box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #1f2937; line-height: 1.7; font-size: 13px; text-align: justify; }
  table { width: 100%; border-collapse: collapse; text-align: left; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: #6366f1; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin: 20px 0 10px; }
  .header-bar { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 3px solid #1f2937; padding-bottom: 10px; margin-bottom: 16px; }
  .header-bar h1 { font-size: 20px; font-weight: bold; color: #111827; margin: 0; }
  .header-bar .meta { font-size: 10px; color: #9ca3af; text-align: right; line-height: 1.6; }
  .profile-grid { display: grid; grid-template-columns: 130px 1fr; gap: 4px 16px; font-size: 13px; margin-bottom: 4px; }
  .profile-label { font-weight: 600; color: #6b7280; }
  .profile-value { color: #1f2937; }
</style></head>
<body>
<div class="header-bar">
  <div><h1>${esc(mn)}</h1><div style="font-size:12px;color:#6b7280;margin-top:2px">Health Profile</div></div>
  <div class="meta">Exported ${now}, ${time}<br>Family Health Manager</div>
</div>
<div class="profile-grid">
  <span class="profile-label">Name</span><span class="profile-value">${esc(mn)}</span>
  <span class="profile-label">Age / Gender</span><span class="profile-value">${age}y &middot; ${GENDER_LABELS[member.gender]}</span>
  ${member.blood_group ? `<span class="profile-label">Blood Group</span><span class="profile-value" style="color:#dc2626;font-weight:bold">${esc(member.blood_group)}</span>` : ""}
</div>
${histParts.length > 0 ? `<h2>Medical History</h2><div style="line-height:1.8;margin-bottom:6px">${histParts.join("<br>")}</div>` : ""}
<h2>Medications (${meds.length})</h2>
<table><thead><tr><th style="${thc}">TYPE</th><th style="${thc}">MEDICINE</th><th style="${thc}">DOSE</th><th style="${thc}">WHEN</th><th style="${thc}">DR.</th><th style="${thc}">DATE</th></tr></thead><tbody>${medRows}</tbody></table>
<div style="margin-top:24px;padding-top:8px;border-top:1px solid #d1d5db;display:flex;justify-content:space-between;font-size:10px;color:#9ca3af">
  <span>Family Health Manager</span><span>Page 1</span>
</div>
</body></html>`;

    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    setTimeout(() => win.print(), 200);
  }

  return (
    <>
      {/* Profile Card */}
      <Card className="shadow-none">
        <CardContent className="p-4 sm:p-5">
          {/* Breadcrumb + actions */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Link to="/members" className="hover:text-primary transition-colors">
                Members
              </Link>
              <span className="text-muted-foreground/30">/</span>
              <span className="text-foreground font-medium">{memberName}</span>
            </div>
            <div className="flex items-center gap-1.5 print:hidden">
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportPDF}
                className="gap-1 h-7 text-xs rounded-lg px-2.5"
              >
                <Printer className="h-3 w-3" />
                PDF
              </Button>
              <Link to={`/members/${member.id}/edit`}>
                <Button variant="outline" size="sm" className="h-7 text-xs rounded-lg px-2.5">
                  Edit
                </Button>
              </Link>
            </div>
          </div>

          {/* Identity | Score */}
          <div className="flex items-center gap-5 mb-4">
            <div className="flex items-center gap-3.5 flex-1 min-w-0">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary font-bold text-xl shrink-0">
                {member.first_name[0]}
                {member.last_name[0]}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold tracking-tight truncate">{memberName}</h1>
                  {riskDot && (
                    <Badge
                      className={`text-[10px] font-bold px-2 py-0.5 ${riskLevel === "high" ? "bg-red-100 text-red-700 border border-red-200" : riskLevel === "moderate" ? "bg-amber-100 text-amber-700 border border-amber-200" : "bg-emerald-100 text-emerald-700 border border-emerald-200"}`}
                    >
                      <span className={`inline-block h-1.5 w-1.5 rounded-full mr-1 ${riskDot}`} />
                      {riskLevel === "high"
                        ? "High"
                        : riskLevel === "moderate"
                          ? "Moderate"
                          : "Low"}{" "}
                      Risk
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    {RELATIONSHIP_LABELS[member.relationship]}
                  </Badge>
                  <span>
                    {age}y · {GENDER_LABELS[member.gender]}
                  </span>
                  {member.blood_group && (
                    <span className="font-semibold text-red-600">{member.blood_group}</span>
                  )}
                </div>
                {medHistoryTags.conditions.length > 0 && (
                  <p className="text-[11px] text-muted-foreground mt-1 truncate">
                    {medHistoryTags.conditions.join(", ")}
                  </p>
                )}
              </div>
            </div>

            <div className="shrink-0 flex flex-col items-center gap-1 p-2 rounded-xl">
              <HealthScoreRing score={health_score} size={68} strokeWidth={4.5} />
              <span className={`text-xs font-bold ${scoreTextColor(health_score)}`}>
                {health_score >= 75 ? "Excellent" : health_score >= 50 ? "Good" : "Needs Attention"}
              </span>
            </div>
          </div>

          {/* Key metrics grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            <div className="rounded-lg bg-muted/40 px-3 py-2">
              <p className="text-lg font-bold">{recent_records.length}</p>
              <p className="text-[10px] text-muted-foreground">Records</p>
            </div>
            <div className="rounded-lg bg-muted/40 px-3 py-2">
              <p className="text-lg font-bold">{active_medications_count}</p>
              <p className="text-[10px] text-muted-foreground">Medications</p>
            </div>
            {active_conditions_count > 0 && (
              <div className="rounded-lg bg-muted/40 px-3 py-2">
                <p className="text-lg font-bold">{active_conditions_count}</p>
                <p className="text-[10px] text-muted-foreground">Conditions</p>
              </div>
            )}
            {provider_assignments && provider_assignments.length > 0 && (
              <div className="rounded-lg bg-muted/40 px-3 py-2">
                <p className="text-lg font-bold">{provider_assignments.length}</p>
                <p className="text-[10px] text-muted-foreground">Providers</p>
              </div>
            )}
            {drug_interactions.length > 0 && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2">
                <p className="text-lg font-bold text-red-700">{drug_interactions.length}</p>
                <p className="text-[10px] text-red-600">Interactions</p>
              </div>
            )}
            {recordsThisMonth > 0 && (
              <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2">
                <p className="text-lg font-bold text-emerald-700">{recordsThisMonth}</p>
                <p className="text-[10px] text-emerald-600">This Month</p>
              </div>
            )}
            {hasAllergies && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
                <p className="text-lg font-bold text-amber-700">{member.allergies!.length}</p>
                <p className="text-[10px] text-amber-600">
                  Allerg{member.allergies!.length !== 1 ? "ies" : "y"}
                </p>
              </div>
            )}
            {lastRecordDate && (
              <div className="rounded-lg bg-muted/40 px-3 py-2">
                <p className="text-xs font-bold">{formatDate(lastRecordDate)}</p>
                <p className="text-[10px] text-muted-foreground">Last Record</p>
              </div>
            )}
          </div>

          {/* Allergies + Surgeries + Emergency */}
          {(medHistoryTags.allergies.length > 0 ||
            medHistoryTags.surgeries.length > 0 ||
            hasEmergency) && (
            <div className="flex items-center gap-3 mt-3 flex-wrap text-xs text-muted-foreground">
              {medHistoryTags.allergies.length > 0 && (
                <span>
                  <span className="font-semibold text-amber-600">Allergies: </span>
                  {medHistoryTags.allergies.join(", ")}
                </span>
              )}
              {medHistoryTags.surgeries.length > 0 && (
                <span>
                  <span className="font-semibold text-purple-600">Surgeries: </span>
                  {medHistoryTags.surgeries.join(", ")}
                </span>
              )}
              {hasEmergency && (
                <span>
                  <Phone className="h-3 w-3 inline mr-1" />
                  {member.emergency_contact_name}
                  {member.emergency_contact_phone && (
                    <span className="ml-1 opacity-60">{member.emergency_contact_phone}</span>
                  )}
                </span>
              )}
            </div>
          )}

          {/* Score breakdown */}
          {score_breakdown && Object.keys(score_breakdown).length > 0 && (
            <div className="mt-3 pt-3 border-t">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2">
                {Object.entries(score_breakdown).map(([key, val]) => {
                  const pct = Math.round((val.score / val.max) * 100);
                  const barColor =
                    pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
                  const textColor =
                    pct >= 80 ? "text-green-600" : pct >= 50 ? "text-amber-600" : "text-red-600";
                  return (
                    <div key={key} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] text-muted-foreground capitalize">
                          {val.label || key.replace(/_/g, " ")}
                        </span>
                        <span className={`text-[11px] font-bold ${textColor}`}>
                          {val.score}/{val.max}
                        </span>
                      </div>
                      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${barColor}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Vitals row */}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
        {member.bmi && (
          <Card className="shadow-none">
            <CardContent className="pt-3 pb-2 text-center">
              <p className="text-lg font-bold tracking-tight">{member.bmi.toFixed(1)}</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                BMI
              </p>
              {member.bmi_category && (
                <p className="text-[10px] font-medium mt-0.5 text-muted-foreground">
                  {member.bmi_category}
                </p>
              )}
            </CardContent>
          </Card>
        )}
        {hba1c_history.length > 0 &&
          (() => {
            const latest = hba1c_history[hba1c_history.length - 1].hba1c_value;
            const cat = getHba1cCategory(latest);
            return (
              <Card className="shadow-none">
                <CardContent className="pt-3 pb-2 text-center">
                  <p className="text-lg font-bold tracking-tight">{latest}%</p>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    HbA1c
                  </p>
                  <p className="text-[10px] font-medium mt-0.5 text-muted-foreground">{cat}</p>
                </CardContent>
              </Card>
            );
          })()}
        <Card className="shadow-none">
          <CardContent className="pt-3 pb-2 text-center">
            <p className="text-lg font-bold tracking-tight">{active_medications_count}</p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Medications
            </p>
          </CardContent>
        </Card>
        {active_conditions_count > 0 && (
          <Card className="shadow-none">
            <CardContent className="pt-3 pb-2 text-center">
              <p className="text-lg font-bold tracking-tight">{active_conditions_count}</p>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Conditions
              </p>
            </CardContent>
          </Card>
        )}
        {hasEmergency && (
          <Card className="shadow-none">
            <CardContent className="pt-3 pb-2 text-center">
              <Phone className="h-3 w-3 mx-auto mb-1 text-muted-foreground" />
              <p className="text-[11px] font-bold truncate">{member.emergency_contact_name}</p>
              {member.emergency_contact_phone && (
                <p className="text-[10px] text-muted-foreground truncate">
                  {member.emergency_contact_phone}
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Quick actions */}
      <div className="flex items-center gap-1 print:hidden">
        {quickActions.map((action) => {
          const Icon = action.icon;
          return (
            <Link
              key={action.hrefSuffix}
              to={`/members/${member.id}${action.hrefSuffix}`}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${action.color}`}
            >
              <Icon className="h-3.5 w-3.5" />
              {action.label}
            </Link>
          );
        })}
      </div>

      {/* Upcoming reminders */}
      {upcoming_reminders.length > 0 && (
        <Card className="shadow-none">
          <CardContent className="pt-4 pb-3 space-y-2.5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Bell className="h-4 w-4 text-blue-500" />
              Upcoming Reminders
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {upcoming_reminders.length}
              </Badge>
            </div>
            <div className="space-y-1.5">
              {upcoming_reminders.map((rem) => (
                <div
                  key={rem.id}
                  className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-xs font-semibold truncate">{rem.title}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {formatRelativeTime(rem.start_datetime!)}
                    </p>
                  </div>
                  <Badge variant="outline" className="text-[10px] shrink-0 ml-2">
                    {rem.reminder_type}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Medications */}
      <ActiveMedicationsTable memberId={member.id} medications={active_medications ?? []} />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Family Member"
        description="Are you sure you want to delete this family member? Their health records will also be removed."
        onConfirm={handleDelete}
      />
    </>
  );
});
