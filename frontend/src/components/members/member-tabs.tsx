import { memo, useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { User, FileText, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { MemberDetailResponse } from "@/lib/types/member";
import { OverviewTab } from "./tabs/overview-tab";
import { RecordsTab } from "./tabs/records-tab";
import { DedupDialog } from "@/components/records/dedup-dialog";

type TabId = "overview" | "records";

const VALID_TABS = new Set<string>(["overview", "records"]);

interface TabConfig {
  id: TabId;
  label: string;
  icon: React.ElementType;
}

const TABS: TabConfig[] = [
  { id: "overview", label: "Overview", icon: User },
  { id: "records", label: "Records", icon: FileText },
];

interface MemberTabsProps {
  data: MemberDetailResponse;
  initialTab?: TabId;
}

export const MemberTabs = memo(function MemberTabs({ data }: MemberTabsProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab") || "overview";
  const activeTab: TabId = VALID_TABS.has(rawTab) ? (rawTab as TabId) : "overview";
  const [dedupOpen, setDedupOpen] = useState(false);

  const handleTabChange = useCallback(
    (tab: TabId) => {
      setSearchParams(tab === "overview" ? {} : { tab }, { replace: true });
    },
    [setSearchParams]
  );

  return (
    <div className="space-y-3 max-w-[1400px] mx-auto">
      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b pb-0">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`
                inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium
                border-b-2 transition-colors cursor-pointer
                ${
                  isActive
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                }
              `}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          );
        })}
        <div className="ml-auto">
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5 border-amber-300 text-amber-700 hover:bg-amber-50"
            onClick={() => setDedupOpen(true)}
          >
            <Copy className="h-3.5 w-3.5" />
            Find Duplicates
          </Button>
        </div>
      </div>

      <DedupDialog open={dedupOpen} onOpenChange={setDedupOpen} memberId={data.member.id} />

      {/* Tab content */}
      <div className="mt-2">
        {activeTab === "overview" && <OverviewTab data={data} />}
        {activeTab === "records" && <RecordsTab data={data} />}
      </div>
    </div>
  );
});
