import useSWR, { mutate } from "swr";
import { useParams, useNavigate } from "react-router-dom";
import { getMember, updateMember } from "@/lib/api/members";
import { MemberForm } from "@/components/members/member-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import type { FamilyMemberUpdate } from "@/lib/types/member";
import type { Gender, Relationship } from "@/lib/types/enums";
import { ErrorState } from "@/components/shared/error-state";

function parseMedicalSummary(summary: string | null) {
  const result = { conditions: "", allergies: "", current_medications: "", past_surgeries: "" };
  if (!summary) return result;
  const keyMap: Record<string, keyof typeof result> = {
    Conditions: "conditions",
    Allergies: "allergies",
    Medications: "current_medications",
    Surgeries: "past_surgeries",
  };
  for (const part of summary.split("; ")) {
    for (const [prefix, field] of Object.entries(keyMap)) {
      if (part.startsWith(`${prefix}:`)) result[field] = part.slice(prefix.length + 1).trim();
    }
  }
  return result;
}

export default function EditMemberPage() {
  const { memberId } = useParams<{ memberId: string }>();
  const navigate = useNavigate();

  const {
    data: member,
    error,
    mutate: _revalidate,
  } = useSWR(memberId ? `member-${memberId}` : null, async () => {
    return getMember(memberId!);
  });

  function createAction() {
    return async function (prevState: unknown, formData: FormData) {
      const fields = {
        Conditions: (formData.get("conditions") as string) || "",
        Allergies: (formData.get("allergies") as string) || "",
        Medications: (formData.get("current_medications") as string) || "",
        Surgeries: (formData.get("past_surgeries") as string) || "",
      };
      const medical_history_summary =
        Object.entries(fields)
          .filter(([, v]) => v.trim())
          .map(([k, v]) => `${k}: ${v.trim()}`)
          .join("; ") || null;

      const allergiesRaw = formData.get("allergies_json") as string;
      let allergies = undefined;
      if (allergiesRaw) {
        try {
          const parsed = JSON.parse(allergiesRaw);
          if (Array.isArray(parsed)) allergies = parsed;
        } catch {}
      }
      const heightStr = formData.get("height_cm") as string;
      const weightStr = formData.get("weight_kg") as string;

      try {
        const data: FamilyMemberUpdate = {
          first_name: (formData.get("first_name") as string) || null,
          last_name: (formData.get("last_name") as string) || null,
          date_of_birth: (formData.get("date_of_birth") as string) || null,
          gender: (formData.get("gender") as Gender) || null,
          relationship: (formData.get("relationship") as Relationship) || null,
          medical_history_summary,
          blood_group: (formData.get("blood_group") as string) || null,
          family_history: (formData.get("family_history") as string) || null,
          height_cm: heightStr ? parseFloat(heightStr) : null,
          weight_kg: weightStr ? parseFloat(weightStr) : null,
          allergies,
          emergency_contact_name: (formData.get("emergency_contact_name") as string) || null,
          emergency_contact_phone: (formData.get("emergency_contact_phone") as string) || null,
          notes: (formData.get("notes") as string) || null,
        };
        await updateMember(memberId!, data);
        mutate(`member-${memberId}`);
        mutate(`member-dashboard-${memberId}`);
        mutate("dashboard");
        navigate(`/people/${memberId}`);
        return null;
      } catch (e) {
        return { error: e instanceof Error ? e.message : "Failed to update member" };
      }
    };
  }

  if (error) return <ErrorState onRetry={() => _revalidate()} />;
  if (!member)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );

  const action = createAction();
  const medicalFields = parseMedicalSummary(member.medical_history_summary);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Link to={`/people/${memberId}`} className="text-sm text-muted-foreground hover:underline">
          {member.first_name} {member.last_name}
        </Link>
        <span className="text-sm text-muted-foreground">/</span>
        <h1 className="text-2xl font-bold">Edit Member</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>
            Edit {member.first_name} {member.last_name}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <MemberForm
            action={action}
            member={member}
            defaultValues={{
              first_name: member.first_name,
              last_name: member.last_name,
              date_of_birth: member.date_of_birth,
              gender: member.gender,
              relationship: member.relationship,
              blood_group: member.blood_group || "",
              family_history: member.family_history || "",
              height_cm: member.height_cm != null ? String(member.height_cm) : "",
              weight_kg: member.weight_kg != null ? String(member.weight_kg) : "",
              emergency_contact_name: member.emergency_contact_name || "",
              emergency_contact_phone: member.emergency_contact_phone || "",
              notes: member.notes || "",
              ...medicalFields,
            }}
          />
        </CardContent>
      </Card>
    </div>
  );
}
