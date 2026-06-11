import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Users } from "lucide-react";
import { listMembers } from "@/lib/api/members";
import type { FamilyMemberResponse } from "@/lib/types/member";
import { useEffect, useState } from "react";

interface AiToolsSubPageProps {
  title: string;
  children: React.ReactNode;
}

export function AiToolsSubPage({ title, children }: AiToolsSubPageProps) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const memberId = searchParams.get("memberId") || "";
  const [memberName, setMemberName] = useState<string>("");

  useEffect(() => {
    if (!memberId) return;
    listMembers()
      .then((members: FamilyMemberResponse[]) => {
        const m = members.find((m) => m.id === memberId);
        if (m) setMemberName(`${m.first_name} ${m.last_name}`);
      })
      .catch(() => {});
  }, [memberId]);

  if (!memberId) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Users className="h-10 w-10 text-muted-foreground/30 mb-3" />
        <p className="text-sm font-medium text-muted-foreground">No member selected</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => navigate("/ai-tools")}>
          Back to AI Tools
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Breadcrumb bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link to={`/ai-tools?memberId=${memberId}`} className="hover:underline">
            AI Tools
          </Link>
          <span>/</span>
          <span className="text-foreground font-medium">{title}</span>
        </div>
        <div className="flex items-center gap-2">
          {memberName && (
            <span className="text-xs bg-muted/50 rounded-lg px-2.5 py-1 flex items-center gap-1.5 text-muted-foreground">
              <Users className="h-3 w-3" />
              {memberName}
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={() => navigate(`/ai-tools?memberId=${memberId}`)}
          >
            <ArrowLeft className="h-3 w-3" />
            All Tools
          </Button>
        </div>
      </div>

      {/* Page content */}
      {children}
    </div>
  );
}
