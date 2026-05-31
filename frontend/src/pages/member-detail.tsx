import useSWR from "swr";
import { useParams, useNavigate } from "react-router-dom";
import { getMemberDetail } from "@/lib/api/members";
import { MemberTabs } from "@/components/members/member-tabs";
import { Link } from "react-router-dom";
import { useEffect } from "react";
import { PageLoader } from "@/components/shared/page-loader";

export default function MemberDetailPage() {
  const { memberId } = useParams<{ memberId: string }>();
  const navigate = useNavigate();

  const { data: detail, error } = useSWR(
    memberId ? `member-detail-${memberId}` : null,
    async () => {
      return getMemberDetail(memberId!);
    },
    { revalidateOnMount: true, dedupingInterval: 60_000 }
  );

  useEffect(() => {
    if (error && "status" in error && (error as { status: number }).status === 401)
      navigate("/login");
  }, [error, navigate]);

  if (!detail) {
    return (
      <div className="space-y-4">
        <Link to="/members" className="text-sm text-muted-foreground hover:underline">
          Back to Members
        </Link>
        <PageLoader />
      </div>
    );
  }

  return <MemberTabs data={detail} />;
}
