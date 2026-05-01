"use client";

import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { RecordTypeBadge } from "@/components/records/record-type-badge";
import { StructuredDataDisplay } from "@/components/records/structured-data-display";
import { RecordAttachments } from "@/components/records/record-attachments";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { RECORD_TYPE_LABELS, GENDER_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import { getRecord, deleteRecord } from "@/lib/api/records";
import { getMember } from "@/lib/api/members";
import { Skeleton } from "@/components/ui/skeleton";
import { Pencil, Printer, Trash2 } from "lucide-react";
import { useRecordQuickView } from "./record-quick-view-provider";
import { toast } from "sonner";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import type { FamilyMemberResponse } from "@/lib/types/member";

function computeAge(dob: string): number {
  const today = new Date();
  const birth = new Date(dob);
  let age = today.getFullYear() - birth.getFullYear();
  const m = today.getMonth() - birth.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
  return age;
}

export function RecordQuickView() {
  const { recordId, memberId, isOpen, closeQuickView } = useRecordQuickView();
  const [record, setRecord] = useState<HealthRecordResponse | null>(null);
  const [member, setMember] = useState<FamilyMemberResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const fetchData = useCallback(async () => {
    if (!recordId || !memberId) return;
    setLoading(true);
    try {
      const [rec, mem] = await Promise.all([getRecord(memberId, recordId), getMember(memberId)]);
      setRecord(rec);
      setMember(mem);
    } catch {
      // Silently fail — user can use "View Full Page"
    } finally {
      setLoading(false);
    }
  }, [recordId, memberId]);

  useEffect(() => {
    if (!isOpen || !recordId || !memberId) {
      setRecord(null);
      setMember(null);
      return;
    }
    fetchData();
  }, [isOpen, recordId, memberId, fetchData]);

  async function handleDelete() {
    if (!record || !memberId) return;
    try {
      await deleteRecord(memberId, record.id);
      toast.success("Record deleted");
      closeQuickView();
    } catch {
      toast.error("Failed to delete record");
    }
  }

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && closeQuickView()}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>
            {record ? record.diagnosis || RECORD_TYPE_LABELS[record.record_type] : "Record"}
          </SheetTitle>
          {record && (
            <SheetDescription className="flex items-center gap-2 flex-wrap">
              <RecordTypeBadge type={record.record_type} />
              <span>{formatDate(record.record_date)}</span>
              {record.provider_name && (
                <>
                  <span className="opacity-40">·</span>
                  <span>{record.provider_name}</span>
                </>
              )}
            </SheetDescription>
          )}
        </SheetHeader>

        <div className="px-4 pb-4 flex-1 overflow-y-auto">
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          ) : record && member ? (
            <>
              <StructuredDataDisplay
                recordType={record.record_type}
                clinicalData={record.clinical_data}
                memberName={`${member.first_name} ${member.last_name}`}
                memberAge={computeAge(member.date_of_birth)}
                memberGender={GENDER_LABELS[member.gender] || member.gender}
                memberBloodGroup={member.blood_group || undefined}
                providerName={record.provider_name || undefined}
                recordDate={record.record_date}
                recordTime={record.record_time || undefined}
              />
              <RecordAttachments
                recordId={record.id}
                attachments={record.attachments || []}
                compact
                onAttachmentsChanged={fetchData}
              />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Could not load record.</p>
          )}
        </div>

        {/* Footer actions */}
        {record && memberId && (
          <div className="border-t px-4 py-3 flex gap-2">
            <Link to={`/members/${memberId}/records/${record.id}/edit`} className="flex-1">
              <Button variant="outline" size="sm" className="w-full gap-1.5">
                <Pencil className="h-3.5 w-3.5" />
                Edit
              </Button>
            </Link>
            <Button
              variant="outline"
              size="sm"
              className="flex-1 gap-1.5"
              onClick={() => window.print()}
            >
              <Printer className="h-3.5 w-3.5" />
              Export
            </Button>
            <Button
              variant="destructive"
              size="sm"
              className="flex-1 gap-1.5"
              onClick={() => setDeleteOpen(true)}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </Button>
          </div>
        )}

        <ConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          title="Delete Record"
          description="Are you sure you want to delete this record? This action cannot be undone."
          onConfirm={handleDelete}
        />
      </SheetContent>
    </Sheet>
  );
}
