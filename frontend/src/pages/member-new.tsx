import { useNavigate } from "react-router-dom";
import { createMember } from "@/lib/api/members";
import { MemberForm } from "@/components/members/member-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import type { Gender, Relationship } from "@/lib/types/enums";
import { mutate } from "swr";

function createMemberClientAction(navigate: ReturnType<typeof useNavigate>) {
  return async function (prevState: unknown, formData: FormData) {
    const heightStr = formData.get("height_cm") as string;
    const weightStr = formData.get("weight_kg") as string;
    const allergiesRaw = formData.get("allergies_json") as string;
    let allergies = null;
    if (allergiesRaw) {
      try {
        const parsed = JSON.parse(allergiesRaw);
        if (Array.isArray(parsed) && parsed.length > 0) allergies = parsed;
      } catch {
        /* ignore */
      }
    }

    try {
      const data = {
        first_name: formData.get("first_name") as string,
        last_name: formData.get("last_name") as string,
        date_of_birth: formData.get("date_of_birth") as string,
        gender: formData.get("gender") as Gender,
        relationship: formData.get("relationship") as Relationship,
        height_cm: heightStr ? parseFloat(heightStr) : null,
        weight_kg: weightStr ? parseFloat(weightStr) : null,
        allergies,
        emergency_contact_name: (formData.get("emergency_contact_name") as string) || null,
        emergency_contact_phone: (formData.get("emergency_contact_phone") as string) || null,
        medical_history: {
          conditions: (formData.get("conditions") as string) || null,
          allergies: (formData.get("allergies") as string) || null,
          current_medications: (formData.get("current_medications") as string) || null,
          past_surgeries: (formData.get("past_surgeries") as string) || null,
          blood_group: (formData.get("blood_group") as string) || null,
          family_history: (formData.get("family_history") as string) || null,
        },
      };
      await createMember(data);
      mutate("dashboard");
      mutate("members");
      navigate("/members");
      return null;
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Failed to create member" };
    }
  };
}

export default function NewMemberPage() {
  const navigate = useNavigate();
  const action = createMemberClientAction(navigate);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Link to="/members" className="text-sm text-muted-foreground hover:underline">
          Members
        </Link>
        <span className="text-sm text-muted-foreground">/</span>
        <h1 className="text-2xl font-bold">New Member</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Add Family Member</CardTitle>
        </CardHeader>
        <CardContent>
          <MemberForm action={action} />
        </CardContent>
      </Card>
    </div>
  );
}
