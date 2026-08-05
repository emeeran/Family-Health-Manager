import useSWR from "swr";
import { useParams, useNavigate } from "react-router-dom";
import { getMemberDetail } from "@/lib/api/members";
import { MemberTabs } from "@/components/members/member-tabs";
import { Link } from "react-router-dom";
import { useEffect } from "react";
import { PageLoader } from "@/components/shared/page-loader";
import { Badge } from "@/components/ui/badge";

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
        <Link to="/people" className="text-sm text-muted-foreground hover:underline">
          Back to People
        </Link>
        <PageLoader />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {detail.member.cloud_ai_consent === false && (
        <div className="flex justify-end">
          <Badge variant="secondary" className="bg-amber-100 text-amber-700 text-[10px]">
            Local AI only
          </Badge>
        </div>
      )}
      <MemberTabs data={detail} />
    </div>
  );
}
