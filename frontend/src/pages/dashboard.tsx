import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { getDashboardSummary } from "@/lib/api/dashboard";
import { DashboardContent, DashboardSkeleton } from "@/components/content/dashboard-content";
import { SmartEntryFAB } from "@/components/records/smart-entry";
import { useEffect } from "react";
import type { FamilyMemberResponse } from "@/lib/types/member";

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: summary, error } = useSWR("dashboard", () => getDashboardSummary(), {
    revalidateOnFocus: false,
    dedupingInterval: 30_000,
  });

  useEffect(() => {
    if (
      error?.message === "Not authenticated" ||
      (error && "status" in error && (error as { status: number }).status === 401)
    ) {
      navigate("/login");
    }
  }, [error, navigate]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <p className="text-lg font-semibold text-destructive mb-2">Failed to load dashboard</p>
        <p className="text-sm text-muted-foreground mb-4">{error.message}</p>
        <button
          onClick={() => navigate("/login")}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Log in again
        </button>
      </div>
    );
  }

  if (!summary) return <DashboardSkeleton />;

  // Redirect to onboarding if no members
  if (!summary.members || summary.members.length === 0) {
    navigate("/onboarding");
    return null;
  }

  // Map dashboard API members to FamilyMemberResponse shape
  const members = summary.members.map(
    (m): FamilyMemberResponse => ({
      id: m.id,
      household_id: "",
      first_name: m.first_name,
      last_name: m.last_name,
      date_of_birth: m.date_of_birth,
      gender: m.gender as FamilyMemberResponse["gender"],
      relationship: m.relationship as FamilyMemberResponse["relationship"],
      medical_history_summary: null,
      blood_group: m.blood_group,
      family_history: null,
      height_cm: null,
      weight_kg: null,
      allergies: m.allergies ?? null,
      emergency_contact_name: null,
      emergency_contact_phone: null,
      bmi: m.bmi,
      bmi_category: null,
      is_active: m.is_active,
      created_at: "",
    })
  );
  const records = (summary.recent_records || []) as unknown as HealthRecordResponse[];

  return (
    <>
      <DashboardContent
        members={members}
        householdName={summary.household_name || "My Family"}
        stats={{
          providersCount: summary.providers_count || 0,
          conversationsCount: summary.conversations_count || 0,
          unreadNotifications: summary.unread_notifications || 0,
          upcomingReminders: summary.upcoming_reminders || [],
        }}
        records={records}
      />
      <SmartEntryFAB members={members} />
    </>
  );
}
