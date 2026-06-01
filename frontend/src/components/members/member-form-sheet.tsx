import { useNavigate } from "react-router-dom";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { MemberForm } from "@/components/members/member-form";
import { createMember } from "@/lib/api/members";
import { mutate } from "swr";
import type { Gender, Relationship } from "@/lib/types/enums";

interface MemberFormSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MemberFormSheet({ open, onOpenChange }: MemberFormSheetProps) {
  const navigate = useNavigate();

  async function action(prevState: unknown, formData: FormData) {
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
      onOpenChange(false);
      return null;
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Failed to create member" };
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>New Member</SheetTitle>
          <SheetDescription>Add a family member to start tracking their health.</SheetDescription>
        </SheetHeader>
        <div className="mt-4">
          <MemberForm action={action} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
