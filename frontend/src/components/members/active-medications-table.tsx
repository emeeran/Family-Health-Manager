import { useState, useCallback, useMemo, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import {
  addMedication,
  updateMedication,
  deleteMedication,
  bulkDeleteMedications,
  getMemberDashboard,
} from "@/lib/api/members";
import { toast } from "sonner";
import { Plus, Loader2, Pencil, Trash2, Download, Pill, Search, GripVertical } from "lucide-react";
import type { ActiveMedication } from "@/lib/types/member";

interface ActiveMedicationsTableProps {
  memberId: string;
  medications: ActiveMedication[];
}

const TYPE_COLORS: Record<string, string> = {
  Tab: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  Cap: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  Inj: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  Syp: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  Cream: "bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300",
  Drops: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
  Inhaler: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
};

const TIMING_LABELS: Record<string, string> = {
  before_food: "Before food",
  after_food: "After food",
  with_food: "With food",
  empty_stomach: "Empty stomach",
  bedtime: "Bedtime",
  sos: "SOS",
  stat: "Stat",
};

/** Format dosage into consistent "M - A - N" pattern. */
function formatDose(raw: string): string {
  const parts = raw.split("-").map((s) => s.trim());
  if (parts.length === 0) return raw;
  // Pad to 3 slots (morning - afternoon - night)
  const slots = [...parts];
  while (slots.length < 3) slots.push("0");
  return slots.slice(0, 3).join(" - ");
}

const TYPE_OPTIONS = ["Tab", "Cap", "Inj", "Syp", "Cream", "Drops", "Inhaler", "Other"];
const TIMING_OPTIONS = [
  { value: "before_food", label: "Before Food" },
  { value: "after_food", label: "After Food" },
  { value: "with_food", label: "With Food" },
  { value: "empty_stomach", label: "Empty Stomach" },
  { value: "bedtime", label: "Bedtime" },
  { value: "sos", label: "SOS" },
  { value: "stat", label: "Stat" },
  { value: "custom", label: "Custom" },
];

interface RxFormData {
  type: string;
  medicine: string;
  dosage: string;
  duration: string;
  timing: string;
  note: string;
}

const emptyRx: RxFormData = {
  type: "Tab",
  medicine: "",
  dosage: "",
  duration: "",
  timing: "",
  note: "",
};

function RxForm({
  initial,
  onSave,
  onCancel,
  loading,
}: {
  initial: RxFormData;
  onSave: (data: RxFormData) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [form, setForm] = useState<RxFormData>(initial);
  const [customTiming, setCustomTiming] = useState(
    () => !!initial.timing && !TIMING_OPTIONS.some((t) => t.value === initial.timing)
  );

  return (
    <div className="border border-primary/30 rounded-lg bg-primary/5 p-3 space-y-2">
      <div className="grid grid-cols-[60px_1fr_80px_120px_1fr] gap-2 items-end">
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Type
          </label>
          <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v ?? "" })}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPE_OPTIONS.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Medicine + Strength
          </label>
          <Input
            className="h-8 text-xs"
            placeholder="e.g. Syndopa 110"
            value={form.medicine}
            onChange={(e) => setForm({ ...form, medicine: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Dosage
          </label>
          <Input
            className="h-8 text-xs"
            placeholder="1-1-1"
            value={form.dosage}
            onChange={(e) => setForm({ ...form, dosage: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Timing
          </label>
          {!customTiming ? (
            <Select
              value={form.timing || undefined}
              onValueChange={(v) => {
                if (v === "custom") {
                  setCustomTiming(true);
                  setForm({ ...form, timing: "" });
                } else {
                  setForm({ ...form, timing: v ?? "" });
                }
              }}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="Select" />
              </SelectTrigger>
              <SelectContent>
                {TIMING_OPTIONS.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <div className="flex gap-1">
              <Input
                className="h-8 text-xs"
                placeholder="e.g. every 6 hours"
                value={form.timing}
                onChange={(e) => setForm({ ...form, timing: e.target.value })}
                autoFocus
              />
              <button
                type="button"
                className="h-8 px-2 text-xs text-muted-foreground hover:text-foreground border rounded-md hover:bg-muted/50 shrink-0"
                onClick={() => {
                  setCustomTiming(false);
                  setForm({ ...form, timing: "" });
                }}
              >
                Back
              </button>
            </div>
          )}
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1 block">
            Note
          </label>
          <Input
            className="h-8 text-xs"
            placeholder="Optional note"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={onCancel}
          disabled={loading}
        >
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          className="h-7 text-xs"
          disabled={loading || !form.medicine.trim()}
          onClick={() => onSave(form)}
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
          Save Medication
        </Button>
      </div>
    </div>
  );
}

export function ActiveMedicationsTable({
  memberId,
  medications: initialMedications,
}: ActiveMedicationsTableProps) {
  const [medications, setMedications] = useState<ActiveMedication[]>(initialMedications);
  const [adding, setAdding] = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [deletingIdx, setDeletingIdx] = useState<number | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [showBulkConfirm, setShowBulkConfirm] = useState(false);
  const [_bulkDeleting, setBulkDeleting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const dragIdxRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const dash = await getMemberDashboard(memberId);
      const meds = dash?.active_medications ?? [];
      setMedications(meds);
    } catch (err) {
      console.error("Refresh medications error:", err);
    }
  }, [memberId]);

  async function handleAdd(data: RxFormData) {
    const nameKey = data.medicine.toLowerCase().trim();
    if (nameKey && medications.some((m) => m.medicine.toLowerCase().trim() === nameKey)) {
      toast.error(`${data.medicine.toUpperCase()} already exists in active prescriptions`);
      return;
    }
    setLoading(true);
    try {
      await addMedication(memberId, data);
      toast.success("Medication added");
      setAdding(false);
      await refresh();
    } catch (err) {
      toast.error("Failed to add medication");
      console.error("Add medication error:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleEdit(idx: number, data: RxFormData) {
    const med = filtered[idx];
    setLoading(true);
    try {
      await updateMedication(memberId, med.record_id, med.prescription_index, data);
      toast.success("Medication updated");
      setEditingIdx(null);
      await refresh();
    } catch {
      toast.error("Failed to update medication");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (deletingIdx === null) return;
    const med = filtered[deletingIdx];
    setLoading(true);
    try {
      await deleteMedication(memberId, med.record_id, med.prescription_index);
      toast.success("Medication removed");
      setDeletingIdx(null);
      setSelectedKeys(new Set());
      await refresh();
    } catch {
      toast.error("Failed to remove medication");
    } finally {
      setLoading(false);
    }
  }

  async function handleBulkDelete() {
    if (selectedKeys.size === 0) return;
    setBulkDeleting(true);
    try {
      const items = Array.from(selectedKeys).map((key) => {
        const [record_id, piStr] = key.split(":");
        return { record_id, prescription_index: parseInt(piStr, 10) };
      });
      const result = await bulkDeleteMedications(memberId, items);
      toast.success(`${result.deleted} medication${result.deleted !== 1 ? "s" : ""} removed`);
      setSelectedKeys(new Set());
      setShowBulkConfirm(false);
      await refresh();
    } catch {
      toast.error("Failed to remove medications");
      await refresh();
    } finally {
      setBulkDeleting(false);
    }
  }

  function toggleSelect(key: string) {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleSelectAll() {
    const allFilteredKeys = filtered.map((m) => m.key);
    const allSelected = allFilteredKeys.every((k) => selectedKeys.has(k));
    if (allSelected) {
      setSelectedKeys(new Set());
    } else {
      setSelectedKeys(new Set(allFilteredKeys));
    }
  }

  function handleDragStart(idx: number) {
    dragIdxRef.current = idx;
  }

  function handleDragOver(e: React.DragEvent, idx: number) {
    e.preventDefault();
    setDragOverIdx(idx);
  }

  function handleDrop(targetIdx: number) {
    const srcIdx = dragIdxRef.current;
    if (srcIdx === null || srcIdx === targetIdx) {
      dragIdxRef.current = null;
      setDragOverIdx(null);
      return;
    }
    // Reorder the underlying `medications` array via enriched list
    const srcKey = filtered[srcIdx].key;
    const targetKey = filtered[targetIdx].key;
    const srcMedIdx = enriched.findIndex((m) => m.key === srcKey);
    const targetMedIdx = enriched.findIndex((m) => m.key === targetKey);
    if (srcMedIdx === -1 || targetMedIdx === -1) return;

    setMedications((prev) => {
      const copy = [...prev];
      // Map enriched index back to original array index
      const srcOrigIdx = prev.findIndex((m) => `${m.record_id}:${m.prescription_index}` === srcKey);
      const targetOrigIdx = prev.findIndex(
        (m) => `${m.record_id}:${m.prescription_index}` === targetKey
      );
      if (srcOrigIdx === -1 || targetOrigIdx === -1) return prev;
      const [moved] = copy.splice(srcOrigIdx, 1);
      // After splice, target shifts if src was before it
      const insertAt = srcOrigIdx < targetOrigIdx ? targetOrigIdx : targetOrigIdx;
      copy.splice(insertAt, 0, moved);
      return copy;
    });

    dragIdxRef.current = null;
    setDragOverIdx(null);
  }

  function handleDragEnd() {
    dragIdxRef.current = null;
    setDragOverIdx(null);
  }

  const enriched = useMemo(
    () =>
      medications.map((m) => ({
        ...m,
        key: `${m.record_id}:${m.prescription_index}`,
      })),
    [medications]
  );

  const filtered = searchQuery.trim()
    ? enriched.filter((m) => {
        const q = searchQuery.toLowerCase();
        return (
          m.medicine.toLowerCase().includes(q) ||
          m.type?.toLowerCase().includes(q) ||
          m.dosage?.toLowerCase().includes(q) ||
          m.note?.toLowerCase().includes(q)
        );
      })
    : enriched;

  function exportPDF() {
    const esc = (s: string) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const rows = filtered
      .map((med) => {
        const typeBadge = esc(med.type || "--");
        const name = esc(med.medicine.toUpperCase());
        const dosage = esc(med.dosage || "--");
        const timing = esc(med.timing ? TIMING_LABELS[med.timing] || med.timing : "--");
        const provider = esc(med.provider_name || "--");
        return `<tr><td style="padding:8px 10px;border-bottom:1px solid #e5e7eb">${typeBadge}</td><td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;font-weight:600">${name}</td><td style="padding:8px 10px;border-bottom:1px solid #e5e7eb">${dosage}</td><td style="padding:8px 10px;border-bottom:1px solid #e5e7eb">${timing}</td><td style="padding:8px 10px;border-bottom:1px solid #e5e7eb">${provider}</td></tr>`;
      })
      .join("");

    const html = `<!DOCTYPE html><html><head><title>Currently Taking Medicine</title>
<style>body{font-family:Arial,sans-serif;padding:30px;color:#1a1a1a}h2{margin:0 0 4px}p.sub{color:#888;margin:0 0 16px;font-size:12px}table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;padding:8px 10px;border-bottom:2px solid #1a1a1a;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#666}</style></head>
<body><h2>Currently Taking Medicine</h2><p class="sub">Exported ${new Date().toLocaleDateString()}</p>
<table><thead><tr><th>Type</th><th>Medicine + Strength</th><th>Dose</th><th>Timing</th><th>Rx By Dr</th></tr></thead><tbody>${rows}</tbody></table>
</body></html>`;

    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    win.print();
  }

  const allFilteredSelected = filtered.length > 0 && filtered.every((m) => selectedKeys.has(m.key));

  return (
    <>
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-100 dark:bg-violet-900/30">
                <Pill className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" />
              </div>
              <CardTitle className="text-sm font-semibold">Currently Taking Medicine</CardTitle>
              {medications.length > 0 && (
                <Badge variant="secondary" className="h-5 text-[10px] font-semibold tabular-nums">
                  {medications.length}
                </Badge>
              )}
            </div>
            {(medications.length > 0 || adding) && (
              <div className="flex items-center gap-1.5">
                {selectedKeys.size > 0 && (
                  <Button
                    variant="destructive"
                    size="sm"
                    className="h-7 text-xs px-2.5"
                    onClick={() => setShowBulkConfirm(true)}
                  >
                    <Trash2 className="h-3 w-3 mr-1" />
                    Delete ({selectedKeys.size})
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs px-2.5"
                  onClick={exportPDF}
                >
                  <Download className="h-3 w-3 mr-1" />
                  PDF
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs px-2.5"
                  onClick={() => setAdding(true)}
                  disabled={adding}
                >
                  <Plus className="h-3 w-3 mr-1" />
                  Add
                </Button>
              </div>
            )}
          </div>
          {medications.length > 3 && (
            <div className="relative mt-2">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search medicines..."
                className="h-8 text-xs pl-8"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          )}
        </CardHeader>
        <CardContent className="pt-0">
          {medications.length === 0 && !adding ? (
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-muted/50 mb-3">
                <Pill className="h-6 w-6 text-muted-foreground/60" />
              </div>
              <p className="text-sm text-muted-foreground mb-3">
                No active prescriptions recorded yet.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={() => setAdding(true)}
              >
                <Plus className="h-3.5 w-3.5 mr-1.5" />
                Add Medicine
              </Button>
            </div>
          ) : (
            <>
              {adding && (
                <div className="mb-3">
                  <RxForm
                    initial={emptyRx}
                    onSave={handleAdd}
                    onCancel={() => setAdding(false)}
                    loading={loading}
                  />
                </div>
              )}

              <div style={{ maxHeight: 320, overflowY: "scroll", overflowX: "auto" }}>
                <table className="w-full text-xs">
                  <colgroup>
                    <col className="w-[18px]" />
                    {/* grip */}
                    <col className="w-[20px]" />
                    {/* checkbox */}
                    <col className="w-[36px]" />
                    {/* type */}
                    <col className="" />
                    {/* medicine — flex */}
                    <col className="w-[88px]" />
                    {/* dose */}
                    <col className="w-[130px]" />
                    {/* when */}
                    <col className="" />
                    {/* note — flex */}
                    <col className="w-[32px]" />
                    {/* dr */}
                    <col className="w-[68px]" />
                    {/* date */}
                    <col className="w-[38px]" />
                    {/* actions */}
                  </colgroup>
                  <thead className="sticky top-0 bg-card z-10 border-b border-border">
                    <tr className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      <th className="py-1" />
                      <th className="py-1">
                        <Checkbox
                          checked={allFilteredSelected}
                          onCheckedChange={toggleSelectAll}
                          className="h-3 w-3"
                        />
                      </th>
                      <th className="py-1 text-left">Type</th>
                      <th className="py-1 px-1.5 text-left">Medicine</th>
                      <th className="py-1 px-1.5 text-left">Dose</th>
                      <th className="py-1 px-1.5 text-left">When</th>
                      <th className="py-1 px-1.5 text-left">Note</th>
                      <th className="py-1 px-1 text-left">Dr.</th>
                      <th className="py-1 px-1 text-left">Date</th>
                      <th className="py-1" />
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((med, idx) => {
                      if (editingIdx === idx) {
                        return (
                          <tr key={`edit-${med.key}`} className="border-b border-border/30">
                            <td colSpan={10} className="p-0">
                              <RxForm
                                initial={{
                                  type: med.type || "Tab",
                                  medicine: med.medicine,
                                  dosage: med.dosage,
                                  duration: "",
                                  timing: med.timing || "",
                                  note: med.note || "",
                                }}
                                onSave={(data) => handleEdit(idx, data)}
                                onCancel={() => setEditingIdx(null)}
                                loading={loading}
                              />
                            </td>
                          </tr>
                        );
                      }

                      return (
                        <tr
                          key={med.key}
                          draggable
                          onDragStart={() => handleDragStart(idx)}
                          onDragOver={(e) => handleDragOver(e, idx)}
                          onDrop={() => handleDrop(idx)}
                          onDragEnd={handleDragEnd}
                          className={`group border-b border-border/10 hover:bg-muted/30 ${selectedKeys.has(med.key) ? "bg-primary/5" : ""} ${dragOverIdx === idx ? "border-t-2 border-t-primary/40" : ""}`}
                        >
                          <td className="py-0.5 cursor-grab active:cursor-grabbing">
                            <GripVertical className="h-3 w-3 text-muted-foreground/30 group-hover:text-muted-foreground/60" />
                          </td>
                          <td className="py-0.5">
                            <Checkbox
                              checked={selectedKeys.has(med.key)}
                              onCheckedChange={() => toggleSelect(med.key)}
                              className="h-3 w-3"
                            />
                          </td>
                          <td className="py-0.5">
                            {med.type ? (
                              <span
                                className={`inline-block px-1 py-px text-[11px] font-bold rounded ${TYPE_COLORS[med.type] || "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"}`}
                              >
                                {med.type}
                              </span>
                            ) : (
                              <span className="text-[11px] text-muted-foreground">--</span>
                            )}
                          </td>
                          <td className="py-0.5 px-1.5">
                            <span
                              className="block truncate font-semibold text-[12px] leading-tight uppercase"
                              title={med.medicine}
                            >
                              {med.medicine}
                            </span>
                          </td>
                          <td className="py-0.5 px-1.5">
                            <span className="whitespace-nowrap text-[11px] tabular-nums font-mono font-medium bg-muted/50 px-1.5 py-px rounded">
                              {med.dosage ? formatDose(med.dosage) : "--"}
                            </span>
                          </td>
                          <td className="py-0.5 px-1.5">
                            <span className="block truncate text-[11px] text-muted-foreground capitalize">
                              {med.timing
                                ? TIMING_LABELS[med.timing] || med.timing.replace(/_/g, " ")
                                : "--"}
                            </span>
                          </td>
                          <td className="py-0.5 px-1.5">
                            {med.note ? (
                              <span
                                className="block truncate text-[11px] text-muted-foreground"
                                title={med.note}
                              >
                                {med.note}
                              </span>
                            ) : (
                              <span className="text-[11px] text-muted-foreground">--</span>
                            )}
                          </td>
                          <td className="py-0.5 px-1">
                            {med.provider_name ? (
                              <span
                                className="block truncate text-[11px] font-semibold"
                                title={med.provider_name}
                              >
                                {med.provider_name
                                  .replace(/^(Dr\.?\s*)/i, "")
                                  .split(/\s+/)
                                  .filter(Boolean)
                                  .map((w) => w[0])
                                  .join("")
                                  .toUpperCase()}
                              </span>
                            ) : (
                              <span className="text-[11px] text-muted-foreground">--</span>
                            )}
                          </td>
                          <td className="py-0.5 px-1 whitespace-nowrap text-[11px] text-muted-foreground tabular-nums">
                            {med.prescribed_date
                              ? new Date(med.prescribed_date).toLocaleDateString("en-GB", {
                                  day: "2-digit",
                                  month: "short",
                                  year: "numeric",
                                })
                              : "--"}
                          </td>
                          <td className="py-0.5 text-right">
                            <div className="flex items-center justify-end gap-px opacity-0 group-hover:opacity-100 transition-opacity">
                              <button
                                className="inline-flex items-center justify-center h-5 w-5 rounded text-muted-foreground hover:text-blue-600 hover:bg-blue-50 transition-colors"
                                onClick={() => setEditingIdx(idx)}
                                title="Edit"
                              >
                                <Pencil className="h-2.5 w-2.5" />
                              </button>
                              <button
                                className="inline-flex items-center justify-center h-5 w-5 rounded text-muted-foreground hover:text-red-600 hover:bg-red-50 transition-colors"
                                onClick={() => setDeletingIdx(idx)}
                                title="Delete"
                              >
                                <Trash2 className="h-2.5 w-2.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {filtered.length === 0 && searchQuery && (
                      <tr>
                        <td colSpan={10} className="py-6 text-center text-xs text-muted-foreground">
                          No medicines matching &quot;{searchQuery}&quot;
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deletingIdx !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingIdx(null);
        }}
        title="Remove Medication"
        description={`Remove ${deletingIdx !== null ? filtered[deletingIdx]?.medicine?.toUpperCase() : "this medication"} from active prescriptions?`}
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={showBulkConfirm}
        onOpenChange={(open) => {
          if (!open) setShowBulkConfirm(false);
        }}
        title={`Remove ${selectedKeys.size} Medication${selectedKeys.size > 1 ? "s" : ""}`}
        description={`Remove ${selectedKeys.size} selected medication${selectedKeys.size > 1 ? "s" : ""} from active prescriptions? This cannot be undone.`}
        onConfirm={handleBulkDelete}
      />
    </>
  );
}
