import useSWR from "swr";
import { useNavigate } from "react-router-dom";
import { getDashboardSummary } from "@/lib/api/dashboard";
import { HomeContent, HomeSkeleton } from "@/components/content/home-content";
import { useEffect } from "react";

export default function HomePage() {
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
        <p className="text-lg font-semibold text-destructive mb-2">Failed to load</p>
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

  if (!summary) return <HomeSkeleton />;

  // Redirect to onboarding if no members (in useEffect to avoid render-time navigation)
  useEffect(() => {
    if (summary && (!summary.members || summary.members.length === 0)) {
      navigate("/onboarding");
    }
  }, [summary, navigate]);

  if (!summary.members || summary.members.length === 0) {
    return <HomeSkeleton />;
  }

  return <HomeContent summary={summary} />;
}
