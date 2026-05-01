import { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, FileText, Search, Upload, Trash2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { RecordsTable } from "@/components/records/records-table";
import { RECORD_TYPE_LABELS } from "@/lib/constants";
import { cleanupEmptyRecords } from "@/lib/api/records";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";
import type { RecordType } from "@/lib/types/enums";

interface RecordsListContentProps {
  records: HealthRecordResponse[];
  member: FamilyMemberResponse;
  onRefresh?: () => void;
}

export function RecordsListContent({ records, member, onRefresh }: RecordsListContentProps) {
  const navigate = useNavigate();
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [searchText, setSearchText] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [showCleanup, setShowCleanup] = useState(false);

  const allTags = useMemo(() => {
    const set = new Set<string>();
    for (const r of records) {
      if (r.tags) for (const t of r.tags) set.add(t);
    }
    return Array.from(set).sort();
  }, [records]);

  const filtered = useMemo(() => {
    return records.filter((r) => {
      if (typeFilter && r.record_type !== typeFilter) return false;
      if (dateFrom && r.record_date < dateFrom) return false;
      if (dateTo && r.record_date > dateTo) return false;
      if (tagFilter && (!r.tags || !r.tags.includes(tagFilter))) return false;
      if (searchText) {
        const lower = searchText.toLowerCase();
        const match =
          r.clinical_data.toLowerCase().includes(lower) ||
          (r.diagnosis && r.diagnosis.toLowerCase().includes(lower)) ||
          (r.provider_name && r.provider_name.toLowerCase().includes(lower));
        if (!match) return false;
      }
      return true;
    });
  }, [records, typeFilter, dateFrom, dateTo, searchText, tagFilter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/members" className="hover:underline">
          Members
        </Link>
        <span>/</span>
        <Link to={`/members/${member.id}`} className="hover:underline">
          {member.first_name} {member.last_name}
        </Link>
        <span>/</span>
        <span className="text-foreground">Records</span>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Health Records</h1>
        <div className="flex items-center gap-2">
          {records.length > 0 && (
            <Button variant="outline" onClick={() => setShowCleanup(true)}>
              <Trash2 className="h-4 w-4 mr-1" />
              Cleanup
            </Button>
          )}
          <Link to={`/members/${member.id}/records/batch`}>
            <Button variant="outline">
              <Upload className="h-4 w-4 mr-1" />
              Batch Upload
            </Button>
          </Link>
          <Link to={`/members/${member.id}/records/new`}>
            <Button>
              <Plus className="h-4 w-4 mr-1" />
              Add Record
            </Button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="grid gap-4 md:grid-cols-5">
            <div className="space-y-1">
              <Label className="text-xs">Type</Label>
              <Select
                value={typeFilter}
                onValueChange={(v) => setTypeFilter(v === "__all__" ? "" : (v ?? ""))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="All types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">All types</SelectItem>
                  {(Object.entries(RECORD_TYPE_LABELS) as [RecordType, string][]).map(
                    ([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    )
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">From</Label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">To</Label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            {allTags.length > 0 && (
              <div className="space-y-1">
                <Label className="text-xs">Tag</Label>
                <Select
                  value={tagFilter}
                  onValueChange={(v) => setTagFilter(v === "__all__" ? "" : (v ?? ""))}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="All tags" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All tags</SelectItem>
                    {allTags.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1">
              <Label className="text-xs">Search</Label>
              <div className="relative">
                <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
                <Input
                  className="pl-8"
                  placeholder="Search records..."
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Records table */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-12 w-12" />}
          title="No records found"
          description={
            records.length === 0
              ? "Start by adding a health record."
              : "Try adjusting your filters."
          }
          action={
            records.length === 0 ? (
              <Link to={`/members/${member.id}/records/new`}>
                <Button>Add First Record</Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <RecordsTable
          records={filtered}
          onRowClick={(r) => navigate(`/members/${member.id}/records/${r.id}`)}
        />
      )}

      <ConfirmDialog
        open={showCleanup}
        onOpenChange={setShowCleanup}
        title="Remove empty records"
        description="This will remove records that have no clinical data, diagnosis, prescription, or attachments. This cannot be undone."
        confirmLabel="Remove"
        onConfirm={async () => {
          if (!member.id) return;
          const result = await cleanupEmptyRecords(member.id);
          if (result.removed > 0) {
            onRefresh?.();
          }
        }}
      />
    </div>
  );
}
