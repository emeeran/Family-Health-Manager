import useSWR from "swr";
import { useParams, useNavigate } from "react-router-dom";
import { getMemberDashboard } from "@/lib/api/members";
import { MemberDashboardContent } from "@/app/(app)/members/[memberId]/dashboard-content";
import { Link } from "react-router-dom";
import { useEffect } from "react";

export default function MemberDetailPage() {
  const { memberId } = useParams<{ memberId: string }>();
  const navigate = useNavigate();

  const { data: dashboard, error } = useSWR(
    memberId ? `member-dashboard-${memberId}` : null,
    async () => {
      return getMemberDashboard(memberId!);
    },
    { revalidateOnMount: true, dedupingInterval: 60_000 }
  );

  useEffect(() => {
    if (error && "status" in error && (error as { status: number }).status === 401)
      navigate("/login");
  }, [error, navigate]);

  if (!dashboard) {
    return (
      <div className="space-y-4">
        <Link to="/members" className="text-sm text-muted-foreground hover:underline">
          Back to Members
        </Link>
        <div className="flex items-center justify-center py-12">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return <MemberDashboardContent dashboard={dashboard} />;
}
