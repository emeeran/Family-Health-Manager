import { memo, useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { QuickLogInput } from "@/components/records/quick-log-input";
import { getLastUsedMember, setLastUsedMember } from "@/lib/member-context";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface QuickLogBarProps {
  activeMembers: FamilyMemberResponse[];
  memberNames: Record<string, string>;
}

export const QuickLogBar = memo(function QuickLogBar({
  activeMembers,
  memberNames,
}: QuickLogBarProps) {
  const [quickLogMemberId, setQuickLogMemberId] = useState<string | null>(null);

  useEffect(() => {
    if (quickLogMemberId) return;
    const last = getLastUsedMember();
    if (last) {
      const match = activeMembers.find((m) => m.id === last.id);
      if (match) setQuickLogMemberId(match.id);
    }
  }, [quickLogMemberId, activeMembers]);

  if (activeMembers.length === 0) return null;

  return (
    <Card className="shadow-none">
      <CardContent className="py-2.5 px-4">
        {quickLogMemberId ? (
          <div className="flex items-center gap-3">
            <button
              onClick={() => setQuickLogMemberId(null)}
              className="text-xs font-medium text-muted-foreground hover:text-foreground shrink-0 underline underline-offset-2"
            >
              Change
            </button>
            <QuickLogInput
              memberId={quickLogMemberId}
              memberName={memberNames[quickLogMemberId]}
              onLogged={() =>
                setLastUsedMember(quickLogMemberId, memberNames[quickLogMemberId] || "")
              }
            />
          </div>
        ) : (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground font-medium">Quick log:</span>
            {activeMembers.slice(0, 5).map((m) => (
              <button
                key={m.id}
                onClick={() => setQuickLogMemberId(m.id)}
                className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-semibold hover:bg-primary hover:text-primary-foreground transition-colors"
              >
                {m.first_name}
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
});
