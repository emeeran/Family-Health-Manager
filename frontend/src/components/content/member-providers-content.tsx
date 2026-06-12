import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ContextualEmptyState } from "@/components/shared/contextual-empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Plus } from "lucide-react";
import { useSWRConfig } from "swr";
import { createAssignment, deleteAssignment } from "@/lib/api/provider-assignments";
import { formatDate } from "@/lib/utils";
import type { ProviderAssignmentResponse } from "@/lib/types/provider-assignment";
import type { ProviderResponse } from "@/lib/types/provider";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface MemberProvidersContentProps {
  assignments: ProviderAssignmentResponse[];
  providers: ProviderResponse[];
  member: FamilyMemberResponse;
}

export function MemberProvidersContent({
  assignments,
  providers,
  member,
}: MemberProvidersContentProps) {
  const { mutate } = useSWRConfig();
  const [selectedProvider, setSelectedProvider] = useState("");
  const [uhidInput, setUhidInput] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteId, setDeleteId] = useState("");
  const [loading, setLoading] = useState(false);

  const assignedIds = new Set(assignments.map((a) => a.provider_id));
  const availableProviders = providers.filter((p) => !assignedIds.has(p.id));

  async function handleAssign() {
    if (!selectedProvider) return;
    setLoading(true);
    try {
      await createAssignment(member.id, {
        provider_id: selectedProvider,
        uhid: uhidInput.trim() || null,
      });
      setSelectedProvider("");
      setUhidInput("");
      await Promise.all([
        mutate(`member-detail-${member.id}`),
        mutate("providers"),
        mutate("dashboard"),
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    await deleteAssignment(member.id, deleteId);
    await Promise.all([
      mutate(`member-detail-${member.id}`),
      mutate("providers"),
      mutate("dashboard"),
    ]);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/people" className="hover:underline">
          Members
        </Link>
        <span>/</span>
        <Link to={`/people/${member.id}`} className="hover:underline">
          {member.first_name} {member.last_name}
        </Link>
        <span>/</span>
        <span className="text-foreground">Providers</span>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Providers</h1>
        <Link to="/providers/new">
          <Button variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-1" />
            New Provider
          </Button>
        </Link>
      </div>

      {availableProviders.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Assign Provider</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs">Provider</Label>
                <Select
                  value={selectedProvider}
                  onValueChange={(v) => setSelectedProvider(v ?? "")}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableProviders.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                        {p.speciality ? ` - ${p.speciality}` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">UHID (Hospital Patient ID)</Label>
                <Input
                  value={uhidInput}
                  onChange={(e) => setUhidInput(e.target.value)}
                  placeholder="e.g. AP-12345"
                  className="h-9"
                />
              </div>
            </div>
            <Button onClick={handleAssign} disabled={!selectedProvider || loading} size="sm">
              Assign
            </Button>
          </CardContent>
        </Card>
      )}

      {assignments.length === 0 && availableProviders.length === 0 ? (
        <ContextualEmptyState variant="no-data" context="provider-assignments" />
      ) : assignments.length === 0 ? null : (
        <div className="grid gap-4 md:grid-cols-2">
          {assignments.map((assignment) => (
            <Card key={assignment.id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">
                    <Link to={`/providers/${assignment.provider_id}`} className="hover:underline">
                      {assignment.provider_name}
                    </Link>
                  </CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => {
                      setDeleteId(assignment.id);
                      setDeleteOpen(true);
                    }}
                  >
                    Unassign
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {assignment.uhid && (
                  <p className="text-sm">
                    <span className="text-muted-foreground">UHID:</span>{" "}
                    <span className="font-mono bg-muted px-1.5 py-0.5 rounded text-xs">
                      {assignment.uhid}
                    </span>
                  </p>
                )}
                <p className="text-xs text-muted-foreground mt-1">
                  Assigned: {formatDate(assignment.created_at)}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Unassign Provider"
        description="Are you sure you want to unassign this provider?"
        confirmLabel="Unassign"
        onConfirm={handleDelete}
      />
    </div>
  );
}
