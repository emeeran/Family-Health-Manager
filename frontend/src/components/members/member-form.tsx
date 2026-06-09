import { useActionState, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  GENDER_LABELS,
  RELATIONSHIP_LABELS,
  BLOOD_GROUP_OPTIONS,
  BMI_CATEGORY_COLORS,
} from "@/lib/constants";
import type { Gender, Relationship } from "@/lib/types/enums";
import type { AllergyEntry, FamilyMemberResponse } from "@/lib/types/member";
import { useDirtyWarn } from "@/hooks/use-dirty-warn";
import { ChevronDown, ChevronRight, Loader2, X } from "lucide-react";

function calcBmi(h: number | null | undefined, w: number | null | undefined): number | null {
  if (h && w && h > 0) {
    const hm = h / 100;
    return Math.round((w / (hm * hm)) * 10) / 10;
  }
  return null;
}

const SEVERITY_COLORS: Record<string, string> = {
  mild: "bg-green-100 text-green-700",
  moderate: "bg-amber-100 text-amber-700",
  severe: "bg-red-100 text-red-700",
};

function AllergyTagInput({
  value,
  onChange,
}: {
  value: AllergyEntry[];
  onChange: (v: AllergyEntry[]) => void;
}) {
  const [name, setName] = useState("");
  const [severity, setSeverity] = useState<"mild" | "moderate" | "severe">("mild");

  function add() {
    const trimmed = name.trim();
    if (!trimmed) return;
    if (value.some((a) => a.name.toLowerCase() === trimmed.toLowerCase())) return;
    onChange([...value, { name: trimmed, severity }]);
    setName("");
    setSeverity("mild");
  }

  function remove(idx: number) {
    onChange(value.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder="e.g. Penicillin, Peanuts"
          className="h-9 flex-1"
        />
        <Select value={severity} onValueChange={(v) => setSeverity(v as typeof severity)}>
          <SelectTrigger className="h-9 w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="mild">Mild</SelectItem>
            <SelectItem value="moderate">Moderate</SelectItem>
            <SelectItem value="severe">Severe</SelectItem>
          </SelectContent>
        </Select>
        <Button type="button" variant="outline" size="sm" onClick={add} className="h-9">
          Add
        </Button>
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {value.map((a, i) => (
            <span
              key={i}
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_COLORS[a.severity] ?? SEVERITY_COLORS.mild}`}
            >
              {a.name}
              <button type="button" onClick={() => remove(i)} className="hover:opacity-70">
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function bmiCategory(bmi: number | null): { label: string; color: string } | null {
  if (bmi === null) return null;
  if (bmi < 18.5) return { label: "Underweight", color: BMI_CATEGORY_COLORS.Underweight };
  if (bmi < 25) return { label: "Normal", color: BMI_CATEGORY_COLORS.Normal };
  if (bmi < 30) return { label: "Overweight", color: BMI_CATEGORY_COLORS.Overweight };
  return { label: "Obese", color: BMI_CATEGORY_COLORS.Obese };
}

const memberSchema = z.object({
  first_name: z.string().min(1, "First name is required").max(50),
  last_name: z.string().min(1, "Last name is required").max(50),
  date_of_birth: z.string().min(1, "Date of birth is required"),
  gender: z.enum(["male", "female", "other", "prefer_not_to_say"] as const),
  relationship: z.enum([
    "self",
    "wife",
    "son",
    "daughter",
    "grand_son",
    "grand_daughter",
    "daughter_in_law",
    "son_in_law",
    "others",
  ] as const),
  height_cm: z.string().optional(),
  weight_kg: z.string().optional(),
  blood_group: z.string().optional(),
  conditions: z.string().optional(),
  allergies: z.string().optional(),
  current_medications: z.string().optional(),
  past_surgeries: z.string().optional(),
  notes: z.string().optional(),
  family_history: z.string().optional(),
  emergency_contact_name: z.string().optional(),
  emergency_contact_phone: z.string().optional(),
});

type MemberFormValues = z.infer<typeof memberSchema>;

interface MemberFormProps {
  action: (prevState: unknown, formData: FormData) => Promise<unknown>;
  defaultValues?: Partial<MemberFormValues>;
  member?: FamilyMemberResponse;
}

export function MemberForm({ action, defaultValues, member }: MemberFormProps) {
  const [showMedical, setShowMedical] = useState(true);
  const [state, formAction, isPending] = useActionState<unknown, FormData>(action, null);
  const [allergyEntries, setAllergyEntries] = useState<AllergyEntry[]>(member?.allergies ?? []);

  const {
    register,
    setValue,
    watch,
    formState: { errors, isDirty },
  } = useForm<MemberFormValues>({
    resolver: zodResolver(memberSchema),
    defaultValues: defaultValues ?? {
      first_name: "",
      last_name: "",
      date_of_birth: "",
      gender: undefined,
      relationship: undefined,
    },
  });

  const allergiesChanged =
    JSON.stringify(allergyEntries) !== JSON.stringify(member?.allergies ?? []);
  useDirtyWarn(isDirty || allergiesChanged, isPending);

  const gender = watch("gender");
  const relationship = watch("relationship");
  const bloodGroup = watch("blood_group");
  const heightRaw = watch("height_cm");
  const weightRaw = watch("weight_kg");

  const heightVal = heightRaw ? parseFloat(heightRaw) : null;
  const weightVal = weightRaw ? parseFloat(weightRaw) : null;
  const liveBmi = calcBmi(heightVal, weightVal);
  const liveCat = bmiCategory(liveBmi);

  return (
    <form action={formAction} className="space-y-4 max-w-2xl">
      {Boolean(state && typeof state === "object" && "error" in (state as object)) && (
        <div
          role="alert"
          className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {String((state as Record<string, unknown>).error ?? "Unknown error")}
        </div>
      )}

      {/* Personal Information */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Personal Information
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="first_name" className="text-xs">
              First Name
            </Label>
            <Input
              id="first_name"
              aria-describedby="err-first_name"
              {...register("first_name")}
              className="h-9"
            />
            {errors.first_name && (
              <p id="err-first_name" role="alert" className="text-[11px] text-destructive">
                {errors.first_name.message}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="last_name" className="text-xs">
              Last Name
            </Label>
            <Input
              id="last_name"
              aria-describedby="err-last_name"
              {...register("last_name")}
              className="h-9"
            />
            {errors.last_name && (
              <p id="err-last_name" role="alert" className="text-[11px] text-destructive">
                {errors.last_name.message}
              </p>
            )}
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="date_of_birth" className="text-xs">
              Date of Birth
            </Label>
            <Input
              id="date_of_birth"
              type="date"
              aria-describedby="err-dob"
              {...register("date_of_birth")}
              className="h-9"
            />
            {errors.date_of_birth && (
              <p id="err-dob" role="alert" className="text-[11px] text-destructive">
                {errors.date_of_birth.message}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Gender</Label>
            <input type="hidden" name="gender" value={gender ?? ""} />
            <Select
              value={gender ?? ""}
              onValueChange={(v) => {
                if (v) setValue("gender", v as Gender);
              }}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select" />
              </SelectTrigger>
              <SelectContent>
                {(Object.entries(GENDER_LABELS) as [Gender, string][]).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.gender && (
              <p id="err-gender" role="alert" className="text-[11px] text-destructive">
                {errors.gender.message}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Relationship</Label>
            <input type="hidden" name="relationship" value={relationship ?? ""} />
            <Select
              value={relationship ?? ""}
              onValueChange={(v) => {
                if (v) setValue("relationship", v as Relationship);
              }}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select" />
              </SelectTrigger>
              <SelectContent>
                {(Object.entries(RELATIONSHIP_LABELS) as [Relationship, string][]).map(
                  ([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  )
                )}
              </SelectContent>
            </Select>
            {errors.relationship && (
              <p id="err-relationship" role="alert" className="text-[11px] text-destructive">
                {errors.relationship.message}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Physical Profile */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Physical Profile
        </p>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="space-y-1">
            <Label htmlFor="height_cm" className="text-xs">
              Height (cm)
            </Label>
            <Input
              id="height_cm"
              type="number"
              step="0.1"
              min="30"
              max="300"
              {...register("height_cm")}
              className="h-9"
              placeholder="e.g. 170"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="weight_kg" className="text-xs">
              Weight (kg)
            </Label>
            <Input
              id="weight_kg"
              type="number"
              step="0.1"
              min="1"
              max="500"
              {...register("weight_kg")}
              className="h-9"
              placeholder="e.g. 70"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Blood Group</Label>
            <input type="hidden" name="blood_group" value={bloodGroup ?? ""} />
            <Select
              value={bloodGroup ?? "__none__"}
              onValueChange={(v) => {
                setValue("blood_group", v === "__none__" ? "" : (v as string | undefined));
              }}
            >
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Not set</SelectItem>
                {BLOOD_GROUP_OPTIONS.map((bg) => (
                  <SelectItem key={bg} value={bg}>
                    {bg}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">BMI</Label>
            <div className="flex items-center gap-2 h-9">
              {liveBmi !== null ? (
                <>
                  <span className="text-sm font-medium">{liveBmi}</span>
                  {liveCat && (
                    <Badge
                      variant="secondary"
                      className={`text-[10px] px-1.5 py-0 ${liveCat.color}`}
                    >
                      {liveCat.label}
                    </Badge>
                  )}
                </>
              ) : (
                <span className="text-xs text-muted-foreground">Enter height & weight</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Medical History - Expandable */}
      <div>
        <button
          type="button"
          onClick={() => setShowMedical(!showMedical)}
          className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
        >
          {showMedical ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Medical History
        </button>
        {showMedical && (
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="conditions" className="text-xs">
                Conditions
              </Label>
              <Textarea
                id="conditions"
                {...register("conditions")}
                rows={2}
                placeholder="e.g., Diabetes, Hypertension"
                className="text-sm min-h-[60px]"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Allergies</Label>
              <input type="hidden" name="allergies_json" value={JSON.stringify(allergyEntries)} />
              <AllergyTagInput value={allergyEntries} onChange={setAllergyEntries} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="current_medications" className="text-xs">
                Current Medications
              </Label>
              <Textarea
                id="current_medications"
                {...register("current_medications")}
                rows={2}
                placeholder="List current medications"
                className="text-sm min-h-[60px]"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="past_surgeries" className="text-xs">
                Past Surgeries
              </Label>
              <Textarea
                id="past_surgeries"
                {...register("past_surgeries")}
                rows={2}
                placeholder="List past surgeries"
                className="text-sm min-h-[60px]"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="notes" className="text-xs">
                Notes
              </Label>
              <Textarea
                id="notes"
                {...register("notes")}
                rows={2}
                placeholder="Any additional notes"
                className="text-sm min-h-[60px]"
              />
            </div>
            <div className="space-y-1 md:col-span-2">
              <Label htmlFor="family_history" className="text-xs">
                Family Medical History
              </Label>
              <Textarea
                id="family_history"
                {...register("family_history")}
                rows={2}
                placeholder="e.g., Father - Diabetes, Mother - Hypertension"
                className="text-sm min-h-[60px]"
              />
            </div>
          </div>
        )}
      </div>

      {/* Emergency Contact */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Emergency Contact
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="emergency_contact_name" className="text-xs">
              Contact Name
            </Label>
            <Input
              id="emergency_contact_name"
              {...register("emergency_contact_name")}
              className="h-9"
              placeholder="e.g. John Doe"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="emergency_contact_phone" className="text-xs">
              Phone Number
            </Label>
            <Input
              id="emergency_contact_phone"
              {...register("emergency_contact_phone")}
              className="h-9"
              placeholder="e.g. +91 9876543210"
            />
          </div>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <Button type="submit" disabled={isPending} size="sm">
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {isPending ? "Saving..." : member ? "Update Member" : "Add Member"}
        </Button>
      </div>
    </form>
  );
}
