import { useState, useMemo } from "react";
import { FileText, Search } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { ExportButton } from "@/components/shared/export-button";
import { RecordsTable } from "@/components/records/records-table";
import { useRecordQuickView } from "@/components/records/record-quick-view-provider";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface HouseholdRecordsContentProps {
  records: HealthRecordResponse[];
  memberNames: Record<string, string>;
  members: FamilyMemberResponse[];
}

export function HouseholdRecordsContent({
  records,
  memberNames,
  members,
}: HouseholdRecordsContentProps) {
  const [searchText, setSearchText] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [memberFilter, setMemberFilter] = useState<string>("all");
  const { openQuickView } = useRecordQuickView();

  const filtered = useMemo(() => {
    return records.filter((r) => {
      if (typeFilter !== "all" && r.record_type !== typeFilter) return false;
      if (memberFilter !== "all" && r.family_member_id !== memberFilter) return false;
      if (searchText.trim()) {
        const q = searchText.toLowerCase();
        const matchesDiagnosis = (r.diagnosis || "").toLowerCase().includes(q);
        const matchesClinical = (r.clinical_data || "").toLowerCase().includes(q);
        const matchesMember = (memberNames[r.family_member_id] || "").toLowerCase().includes(q);
        return matchesDiagnosis || matchesClinical || matchesMember;
      }
      return true;
    });
  }, [records, searchText, typeFilter, memberFilter, memberNames]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">All Records</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {records.length} record{records.length !== 1 ? "s" : ""} across all family members
          </p>
        </div>
        <ExportButton />
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search records..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={typeFilter} onValueChange={(v) => setTypeFilter(v ?? "all")}>
          <SelectTrigger className="w-full sm:w-44">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            {Object.entries(RECORD_TYPE_LABELS).map(([key, label]) => (
              <SelectItem key={key} value={key}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={memberFilter} onValueChange={(v) => setMemberFilter(v ?? "all")}>
          <SelectTrigger className="w-full sm:w-48">
            <SelectValue placeholder="All members" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Members</SelectItem>
            {members.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.first_name} {m.last_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Results */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-12 w-12" />}
          title={records.length === 0 ? "No records yet" : "No matching records"}
          description={
            records.length === 0
              ? "Health records will appear here as you add them."
              : "Try adjusting your filters."
          }
        />
      ) : (
        <RecordsTable
          records={filtered}
          memberNames={memberNames}
          onRowClick={(r) => openQuickView(r.id, r.family_member_id)}
        />
      )}
    </div>
  );
}

export function HouseholdRecordsSkeleton() {
  return (
    <div className="space-y-6">
      <div>
        <Skeleton className="h-7 w-28 mb-1" />
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="flex gap-3">
        <Skeleton className="h-9 flex-1" />
        <Skeleton className="h-9 w-44" />
        <Skeleton className="h-9 w-48" />
      </div>
      <Card>
        <CardContent className="p-0">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 px-4 py-3">
              <Skeleton className="h-5 w-20 rounded-full" />
              <div className="flex-1">
                <Skeleton className="h-4 w-48 mb-1" />
                <Skeleton className="h-3 w-32" />
              </div>
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
