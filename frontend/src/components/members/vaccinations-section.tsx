import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { listVaccinations, createVaccination, deleteVaccination } from "@/lib/api/vaccinations";
import { formatDate } from "@/lib/utils";
import { Syringe, Plus, Loader2, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import type { VaccinationResponse } from "@/lib/types/vaccination";

interface VaccinationsSectionProps {
  memberId: string;
}

function isOverdue(dateStr: string | null): boolean {
  if (!dateStr) return false;
  return new Date(dateStr) < new Date();
}

export function VaccinationsSection({ memberId }: VaccinationsSectionProps) {
  const [vaccinations, setVaccinations] = useState<VaccinationResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<VaccinationResponse | null>(null);

  // Form fields
  const [name, setName] = useState("");
  const [dateAdmin, setDateAdmin] = useState("");
  const [boosterDate, setBoosterDate] = useState("");
  const [notes, setNotes] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await listVaccinations(memberId);
      setVaccinations(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [memberId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAdd() {
    if (!name.trim() || !dateAdmin) return;
    setSaving(true);
    try {
      await createVaccination(memberId, {
        name: name.trim(),
        date_administered: dateAdmin,
        booster_due_date: boosterDate || null,
        notes: notes.trim() || null,
      });
      setName("");
      setDateAdmin("");
      setBoosterDate("");
      setNotes("");
      setShowForm(false);
      await load();
      toast.success("Vaccination added");
    } catch {
      toast.error("Failed to add vaccination");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteVaccination(memberId, deleteTarget.id);
      setDeleteTarget(null);
      await load();
      toast.success("Vaccination deleted");
    } catch {
      toast.error("Failed to delete vaccination");
    }
  }

  const overdueCount = vaccinations.filter((v) => isOverdue(v.booster_due_date)).length;

  if (loading) {
    return (
      <Card className="flex flex-col overflow-hidden">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Syringe className="h-4 w-4 text-teal-600" />
            Vaccinations
          </CardTitle>
        </CardHeader>
        <CardContent className="flex-1">
          <div className="flex items-center gap-2 py-4 text-foreground/50">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-xs">Loading...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="flex flex-col overflow-hidden">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Syringe className="h-4 w-4 text-teal-600" />
              Vaccinations
              {vaccinations.length > 0 && (
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                  {vaccinations.length}
                </Badge>
              )}
              {overdueCount > 0 && (
                <Badge className="text-[10px] bg-red-100 text-red-800 font-bold px-1.5 py-0">
                  {overdueCount} overdue
                </Badge>
              )}
            </CardTitle>
            {!showForm && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowForm(true)}
                className="h-7 text-xs gap-1"
              >
                <Plus className="h-3 w-3" /> Add
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex-1">
          {showForm && (
            <div className="space-y-2 mb-3 p-3 rounded-lg border bg-muted/30">
              <div className="grid gap-2 grid-cols-2">
                <div>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="h-7 text-xs"
                    placeholder="Vaccine name"
                  />
                </div>
                <div>
                  <Input
                    type="date"
                    value={dateAdmin}
                    onChange={(e) => setDateAdmin(e.target.value)}
                    className="h-7 text-xs"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <Input
                  type="date"
                  value={boosterDate}
                  onChange={(e) => setBoosterDate(e.target.value)}
                  className="h-7 text-xs flex-1"
                  placeholder="Booster due"
                />
                <Button
                  size="sm"
                  className="h-7 text-xs px-3"
                  onClick={handleAdd}
                  disabled={saving || !name.trim() || !dateAdmin}
                >
                  {saving && <Loader2 className="h-3 w-3 animate-spin mr-1" />}
                  Save
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2"
                  onClick={() => setShowForm(false)}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}

          {vaccinations.length === 0 && !showForm ? (
            <p className="text-xs text-muted-foreground py-2">No vaccinations recorded</p>
          ) : (
            <div className="space-y-1">
              {vaccinations.map((v) => {
                const overdue = isOverdue(v.booster_due_date);
                return (
                  <div
                    key={v.id}
                    className={`flex items-center justify-between rounded-lg px-2.5 py-1.5 text-xs ${overdue ? "bg-red-50 border border-red-200 dark:bg-red-950/30 dark:border-red-800" : "hover:bg-muted/30"}`}
                  >
                    <div className="min-w-0">
                      <span className="font-medium">{v.name}</span>
                      <span className="text-muted-foreground ml-1.5">
                        {formatDate(v.date_administered)}
                        {v.booster_due_date && (
                          <>
                            {" · "}
                            <span className={overdue ? "text-red-700 font-bold" : ""}>
                              {overdue ? "OVERDUE" : formatDate(v.booster_due_date)}
                            </span>
                          </>
                        )}
                      </span>
                    </div>
                    <button
                      className="p-1 rounded text-muted-foreground/40 hover:text-destructive shrink-0"
                      onClick={() => setDeleteTarget(v)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Delete Vaccination"
        description={`Remove "${deleteTarget?.name}" from the record?`}
        onConfirm={handleDelete}
      />
    </>
  );
}
