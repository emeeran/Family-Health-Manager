import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Heart,
  Users,
  Stethoscope,
  Sparkles,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
} from "lucide-react";
import { updateHousehold } from "@/lib/api/household";
import { createMember } from "@/lib/api/members";
import { createProvider } from "@/lib/api/providers";
import { toast } from "sonner";
import type { Gender, Relationship } from "@/lib/types/enums";

interface OnboardingWizardProps {
  householdName: string;
}

const STEPS = [
  { title: "Welcome", icon: Heart },
  { title: "Family Member", icon: Users },
  { title: "Provider", icon: Stethoscope },
  { title: "Ready", icon: Sparkles },
];

export function OnboardingWizard({ householdName: initialName }: OnboardingWizardProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  // Step 1: Household name
  const [name, setName] = useState(initialName);

  // Step 2: First family member
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [dob, setDob] = useState("");
  const [gender, setGender] = useState<Gender>("male");
  const [relationship, setRelationship] = useState<Relationship>("self");

  // Step 3: First provider (optional)
  const [providerName, setProviderName] = useState("");
  const [providerSpeciality, setProviderSpeciality] = useState("");
  const [providerPhone, setProviderPhone] = useState("");

  async function handleNext() {
    if (step === 0) {
      // Save household name
      if (name.trim()) {
        try {
          await updateHousehold({ name: name.trim() });
        } catch {
          // Non-critical, continue
        }
      }
      setStep(1);
    } else if (step === 1) {
      // Create first family member
      if (!firstName.trim() || !lastName.trim() || !dob) {
        toast.error("Please fill in all required fields");
        return;
      }
      setSaving(true);
      try {
        await createMember({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          date_of_birth: dob,
          gender,
          relationship,
        });
        setStep(2);
      } catch {
        toast.error("Failed to create family member");
      } finally {
        setSaving(false);
      }
    } else if (step === 2) {
      // Optional provider creation
      if (providerName.trim()) {
        setSaving(true);
        try {
          await createProvider({
            name: providerName.trim(),
            speciality: providerSpeciality.trim() || null,
            phone: providerPhone.trim() || null,
          });
        } catch {
          toast.error("Failed to add provider, but you can continue");
        } finally {
          setSaving(false);
        }
      }
      setStep(3);
    } else {
      navigate("/dashboard");
      window.location.reload();
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      {/* Step indicator */}
      <div className="flex items-center justify-center gap-2 pt-4">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const isActive = i === step;
          const isDone = i < step;
          return (
            <div key={i} className="flex items-center gap-2">
              {i > 0 && <div className={`h-px w-8 ${isDone ? "bg-primary" : "bg-border"}`} />}
              <div
                className={`flex h-9 w-9 items-center justify-center rounded-full transition-all ${
                  isActive
                    ? "bg-primary text-primary-foreground shadow-md"
                    : isDone
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground"
                }`}
              >
                {isDone ? <CheckCircle2 className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
              </div>
            </div>
          );
        })}
      </div>

      {/* Step content */}
      <Card>
        <CardHeader className="text-center">
          <CardTitle>{STEPS[step].title}</CardTitle>
          <CardDescription>
            {step === 0 && "Let's set up your family health tracker"}
            {step === 1 && "Add your first family member to get started"}
            {step === 2 && "Add a healthcare provider (optional)"}
            {step === 3 && "You're all set! Let's start tracking health."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {step === 0 && (
            <div className="space-y-2">
              <Label htmlFor="household_name">Household Name</Label>
              <Input
                id="household_name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., The Smith Family"
              />
              <p className="text-xs text-muted-foreground">
                This will be displayed on your dashboard
              </p>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="first_name">First Name</Label>
                  <Input
                    id="first_name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="last_name">Last Name</Label>
                  <Input
                    id="last_name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="dob">Date of Birth</Label>
                <Input
                  id="dob"
                  type="date"
                  value={dob}
                  onChange={(e) => setDob(e.target.value)}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="gender-select">Gender</Label>
                  <Select value={gender} onValueChange={(v) => setGender(v as Gender)}>
                    <SelectTrigger id="gender-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="male">Male</SelectItem>
                      <SelectItem value="female">Female</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                      <SelectItem value="prefer_not_to_say">Prefer not to say</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="relationship-select">Relationship</Label>
                  <Select
                    value={relationship}
                    onValueChange={(v) => setRelationship(v as Relationship)}
                  >
                    <SelectTrigger id="relationship-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="self">Self</SelectItem>
                      <SelectItem value="wife">Wife</SelectItem>
                      <SelectItem value="son">Son</SelectItem>
                      <SelectItem value="daughter">Daughter</SelectItem>
                      <SelectItem value="others">Others</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="provider_name">Provider Name</Label>
                <Input
                  id="provider_name"
                  value={providerName}
                  onChange={(e) => setProviderName(e.target.value)}
                  placeholder="e.g., Dr. Smith"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="provider_speciality">Specialty</Label>
                <Input
                  id="provider_speciality"
                  value={providerSpeciality}
                  onChange={(e) => setProviderSpeciality(e.target.value)}
                  placeholder="e.g., General Physician"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="provider_phone">Phone</Label>
                <Input
                  id="provider_phone"
                  value={providerPhone}
                  onChange={(e) => setProviderPhone(e.target.value)}
                  placeholder="e.g., +1 234 567 8900"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                You can skip this step and add providers later
              </p>
            </div>
          )}

          {step === 3 && (
            <div className="text-center py-4 space-y-4">
              <div className="flex h-16 w-16 mx-auto items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500/20 to-teal-500/20">
                <CheckCircle2 className="h-8 w-8 text-emerald-500" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium">Your health tracker is ready!</p>
                <p className="text-xs text-muted-foreground">
                  Start by adding health records for your family members, or chat with the AI
                  assistant about any health questions.
                </p>
              </div>
            </div>
          )}

          {/* Navigation buttons */}
          <div className="flex justify-between pt-2">
            {step > 0 ? (
              <Button variant="outline" onClick={() => setStep(step - 1)} disabled={saving}>
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back
              </Button>
            ) : (
              <div />
            )}
            <Button onClick={handleNext} disabled={saving}>
              {saving ? (
                "Saving..."
              ) : step === 3 ? (
                "Go to Dashboard"
              ) : step === 2 && !providerName.trim() ? (
                "Skip for now"
              ) : (
                <>
                  Continue
                  <ArrowRight className="h-4 w-4 ml-1" />
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
