import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { getHousehold } from "@/lib/api/household";
import { listMembers } from "@/lib/api/members";
import { OnboardingWizard } from "@/components/content/onboarding-wizard";
import { useEffect } from "react";
import { ErrorState } from "@/components/shared/error-state";

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { data, error, mutate } = useSWR("onboarding", async () => {
    const [household, members] = await Promise.all([getHousehold(), listMembers().catch(() => [])]);
    return { household, members };
  });

  useEffect(() => {
    if (data && data.members.length > 0) navigate("/dashboard");
  }, [data, navigate]);

  if (error)
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <ErrorState onRetry={() => mutate()} />
      </div>
    );
  if (!data)
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  if (data.members.length > 0) return null;
  return <OnboardingWizard householdName={data.household.name} />;
}
