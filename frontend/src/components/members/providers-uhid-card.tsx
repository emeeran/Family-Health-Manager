import { useState, useRef, useEffect, memo } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Stethoscope, Plus, ArrowRight, Check, X } from "lucide-react";
import useSWR from "swr";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { listProviders } from "@/lib/api/providers";
import { createAssignment, updateUhid } from "@/lib/api/provider-assignments";
import type { ProviderResponse } from "@/lib/types/provider";
import type { ProviderAssignmentResponse } from "@/lib/types/provider-assignment";

interface ProvidersUhidCardProps {
  memberId: string;
  assignments: ProviderAssignmentResponse[];
}

export const ProvidersUhidCard = memo(function ProvidersUhidCard({
  memberId,
  assignments: initialAssignments,
}: ProvidersUhidCardProps) {
  const { mutate } = useSWRConfig();
  const assignments = initialAssignments ?? [];

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [adding, setAdding] = useState(false);
  const [newProviderId, setNewProviderId] = useState("");
  const [newUhid, setNewUhid] = useState("");
  const [loading, setLoading] = useState(false);
  const editRef = useRef<HTMLInputElement>(null);

  const { data: providers = [] } = useSWR<ProviderResponse[]>(
    "providers-for-uhid",
    () => {
      return listProviders();
    },
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  );

  const assignedIds = new Set(assignments.map((a) => a.provider_id));
  const available = providers.filter((p) => !assignedIds.has(p.id));

  useEffect(() => {
    if (editingId) editRef.current?.focus();
  }, [editingId]);

  async function handleSave(assignmentId: string) {
    try {
      await updateUhid(memberId, assignmentId, editValue.trim() || null);
      await Promise.all([mutate(`member-detail-${memberId}`), mutate("dashboard")]);
      setEditingId(null);
    } catch {
      toast.error("Failed to update UHID");
    }
  }

  async function handleAssign() {
    if (!newProviderId) return;
    setLoading(true);
    try {
      await createAssignment(memberId, {
        provider_id: newProviderId,
        uhid: newUhid.trim() || null,
      });
      await Promise.all([
        mutate(`member-detail-${memberId}`),
        mutate("providers"),
        mutate("dashboard"),
      ]);
      setAdding(false);
      setNewProviderId("");
      setNewUhid("");
    } catch {
      toast.error("Failed to assign provider");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold">
            Providers & UHIDs
            {assignments.length > 0 && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 ml-2">
                {assignments.length}
              </Badge>
            )}
          </CardTitle>
          {!adding && available.length > 0 && (
            <button onClick={() => setAdding(true)} className="text-primary hover:text-primary/80">
              <Plus className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-2 pt-0">
        {/* Inline assign form */}
        {adding && (
          <div className="space-y-2 pb-2 border-b">
            <Select value={newProviderId} onValueChange={(v) => setNewProviderId(v ?? "")}>
              <SelectTrigger className="h-7 text-xs">
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                {available.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                    {p.speciality ? ` (${p.speciality})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex gap-1">
              <Input
                value={newUhid}
                onChange={(e) => setNewUhid(e.target.value)}
                placeholder="UHID (optional)"
                className="h-7 text-xs font-mono flex-1"
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleAssign();
                }}
              />
              <Button
                size="sm"
                className="h-7 px-2"
                onClick={handleAssign}
                disabled={!newProviderId || loading}
              >
                <Check className="h-3 w-3" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2"
                onClick={() => {
                  setAdding(false);
                  setNewProviderId("");
                  setNewUhid("");
                }}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          </div>
        )}

        {assignments.length === 0 && !adding ? (
          <div className="flex-1 flex flex-col items-center justify-center py-4 text-center">
            <Stethoscope className="h-8 w-8 text-muted-foreground/30 mb-2" />
            <p className="text-xs text-muted-foreground mb-3">No providers assigned</p>
            {providers.length > 0 ? (
              <Button
                variant="outline"
                size="sm"
                className="text-xs h-7"
                onClick={() => setAdding(true)}
              >
                <Plus className="h-3 w-3 mr-1" />
                Assign Provider
              </Button>
            ) : (
              <Link to="/providers/new">
                <Button variant="outline" size="sm" className="text-xs h-7">
                  <Plus className="h-3 w-3 mr-1" />
                  Add Provider
                </Button>
              </Link>
            )}
          </div>
        ) : (
          <>
            <div className="space-y-1.5 flex-1">
              {assignments.map((a) => (
                <div key={a.id} className="flex items-center gap-2 text-xs">
                  <Link
                    to={`/providers/${a.provider_id}`}
                    className="font-medium hover:text-primary transition-colors truncate min-w-0"
                  >
                    {a.provider_name}
                  </Link>
                  {editingId === a.id ? (
                    <div className="flex items-center gap-1 shrink-0">
                      <Input
                        ref={editRef}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSave(a.id);
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        placeholder="UHID"
                        className="h-6 w-24 text-xs font-mono px-1.5"
                      />
                      <button
                        onClick={() => handleSave(a.id)}
                        className="p-0.5 rounded hover:bg-muted text-primary"
                      >
                        <Check className="h-3 w-3" />
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
                        <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">
                          {a.uhid}
                        </code>
                      ) : (
                        <span className="text-primary/60 text-xs border border-dashed border-primary/30 px-1.5 py-0.5 rounded hover:bg-primary/5">
                          + UHID
                        </span>
                      )}
                    </button>
                  )}
                </div>
              ))}
            </div>
            <Link
              to="/providers"
              className="flex items-center justify-center gap-1 pt-2 text-[11px] font-medium text-primary hover:underline"
            >
              Manage
              <ArrowRight className="h-3 w-3" />
            </Link>
          </>
        )}
      </CardContent>
    </Card>
  );
});
