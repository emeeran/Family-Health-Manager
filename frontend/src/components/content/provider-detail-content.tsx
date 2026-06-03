import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Phone, MapPin, Users, Plus, Check, X } from "lucide-react";
import useSWR from "swr";
import { useSWRConfig } from "swr";
import { deleteProvider } from "@/lib/api/providers";
import { listMembers } from "@/lib/api/members";
import { createAssignment, updateUhid } from "@/lib/api/provider-assignments";
import { ApiError } from "@/lib/api-client";
import { formatDate } from "@/lib/utils";
import { toast } from "sonner";
import type { ProviderResponse } from "@/lib/types/provider";
import type { ProviderAssignmentResponse } from "@/lib/types/provider-assignment";
import type { FamilyMemberResponse } from "@/lib/types/member";

interface ProviderDetailContentProps {
  provider: ProviderResponse;
  assignedMembers: ProviderAssignmentResponse[];
}

export function ProviderDetailContent({ provider, assignedMembers }: ProviderDetailContentProps) {
  const navigate = useNavigate();
  const { mutate } = useSWRConfig();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [adding, setAdding] = useState(false);
  const [newMemberId, setNewMemberId] = useState("");
  const [newUhid, setNewUhid] = useState("");
  const [loading, setLoading] = useState(false);
  const editRef = useRef<HTMLInputElement>(null);

  const { data: members = [] } = useSWR<FamilyMemberResponse[]>(
    "members-for-provider-assign",
    () => listMembers(),
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  );

  const assignedIds = new Set(assignedMembers.map((a) => a.family_member_id));
  const available = members.filter((m) => m.is_active && !assignedIds.has(m.id));

  useEffect(() => {
    if (editingId) editRef.current?.focus();
  }, [editingId]);

  async function handleDelete() {
    try {
      await deleteProvider(provider.id);
      toast.success("Provider deleted");
      navigate("/providers");
    } catch {
      toast.error("Failed to delete provider");
    }
  }

  async function handleSaveUhid(assignmentId: string, memberId: string) {
    try {
      try {
        await updateUhid(memberId, assignmentId, editValue.trim() || null);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          await createAssignment(memberId, {
            provider_id: provider.id,
            uhid: editValue.trim() || null,
          });
        } else {
          throw err;
        }
      }
      await mutate(`provider-${provider.id}`);
      setEditingId(null);
    } catch {
      toast.error("Failed to update UHID");
    }
  }

  async function handleAssign() {
    if (!newMemberId) return;
    setLoading(true);
    try {
      await createAssignment(newMemberId, {
        provider_id: provider.id,
        uhid: newUhid.trim() || null,
      });
      await Promise.all([mutate(`provider-${provider.id}`), mutate("providers")]);
      setAdding(false);
      setNewMemberId("");
      setNewUhid("");
    } catch {
      toast.error("Failed to assign member");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/providers" className="hover:underline">
          Providers
        </Link>
        <span>/</span>
        <span className="text-foreground">{provider.name}</span>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{provider.name}</h1>
        <div className="flex gap-2">
          <Link to={`/providers/${provider.id}/edit`}>
            <Button variant="outline">Edit</Button>
          </Link>
          <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
            Delete
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Provider Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {provider.speciality && (
            <>
              <div>
                <span className="text-muted-foreground">Speciality:</span> {provider.speciality}
              </div>
              <Separator />
            </>
          )}
          {provider.phone && (
            <>
              <div className="flex items-center gap-2">
                <Phone className="h-4 w-4 text-muted-foreground" />
                <span>{provider.phone}</span>
              </div>
              <Separator />
            </>
          )}
          {provider.address && (
            <>
              <div className="flex items-start gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                <span className="whitespace-pre-wrap">{provider.address}</span>
              </div>
              <Separator />
            </>
          )}
          <div>
            <span className="text-muted-foreground">Added:</span> {formatDate(provider.created_at)}
          </div>
        </CardContent>
      </Card>

      {/* Assigned Members */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Users className="h-4 w-4" />
              Assigned Members ({assignedMembers.length})
            </CardTitle>
            {!adding && available.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={() => setAdding(true)}
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Inline assign form */}
          {adding && (
            <div className="space-y-2 pb-3 border-b mb-3">
              <Select value={newMemberId} onValueChange={(v) => setNewMemberId(v ?? "")}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder="Select member" />
                </SelectTrigger>
                <SelectContent>
                  {available.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.first_name} {m.last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="flex gap-1">
                <Input
                  value={newUhid}
                  onChange={(e) => setNewUhid(e.target.value)}
                  placeholder="UHID (optional)"
                  className="h-8 text-sm font-mono flex-1"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAssign();
                  }}
                />
                <Button
                  size="sm"
                  className="h-8 px-2"
                  onClick={handleAssign}
                  disabled={!newMemberId || loading}
                >
                  <Check className="h-3.5 w-3.5" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8 px-2"
                  onClick={() => {
                    setAdding(false);
                    setNewMemberId("");
                    setNewUhid("");
                  }}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          {assignedMembers.length === 0 && !adding ? (
            <div className="flex flex-col items-center justify-center py-4 text-center">
              <p className="text-sm text-muted-foreground mb-3">
                No family members assigned to this provider yet.
              </p>
              {available.length > 0 ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-sm h-8"
                  onClick={() => setAdding(true)}
                >
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  Assign Member
                </Button>
              ) : (
                <p className="text-xs text-muted-foreground">No members available to assign.</p>
              )}
            </div>
          ) : (
            <div className="divide-y">
              {assignedMembers.map((a) => (
                <div key={a.id} className="flex items-center gap-2 py-2.5 first:pt-0 last:pb-0">
                  <Link to={`/people/${a.family_member_id}`} className="min-w-0 hover:underline">
                    <span className="text-sm font-medium truncate">{a.family_member_name}</span>
                  </Link>
                  {editingId === a.id ? (
                    <div className="flex items-center gap-1 shrink-0">
                      <Input
                        ref={editRef}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSaveUhid(a.id, a.family_member_id);
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        placeholder="UHID"
                        className="h-7 w-28 text-xs font-mono px-1.5"
                      />
                      <button
                        onClick={() => handleSaveUhid(a.id, a.family_member_id)}
                        className="p-0.5 rounded hover:bg-muted text-primary"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="p-0.5 rounded hover:bg-muted text-muted-foreground"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setEditingId(a.id);
                        setEditValue(a.uhid || "");
                      }}
                      className="shrink-0"
                    >
                      {a.uhid ? (
                        <code className="bg-muted px-4 py-0.5 rounded text-xs font-mono min-w-16 text-center inline-block">
                          {a.uhid}
                        </code>
                      ) : (
                        <span className="text-primary/60 text-xs border border-dashed border-primary/30 px-2 py-0.5 rounded hover:bg-primary/5">
                          + UHID
                        </span>
                      )}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete Provider"
        description="Are you sure you want to delete this provider? This will not affect existing records."
        onConfirm={handleDelete}
      />
    </div>
  );
}
