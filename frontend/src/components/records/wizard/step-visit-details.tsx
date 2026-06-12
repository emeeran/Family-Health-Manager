import { memo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Plus, X } from "lucide-react";
import type { ProviderResponse } from "@/lib/types/provider";

interface StepVisitDetailsProps {
  providers: ProviderResponse[];
  register: any;
  isDoctorVisit: boolean;
  showProviderSelect: boolean;
  onAddProvider: () => void;
  chiefComplaint: string;
  onChiefComplaintChange: (value: string) => void;
  diagnosis: string;
  nextReviewDate: string;
  notes: string;
  onNotesChange: (value: string) => void;
  tags: string[];
  onTagsChange: (tags: string[]) => void;
  tagInput: string;
  onTagInputChange: (value: string) => void;
  providerLabel?: string;
}

export const StepVisitDetails = memo(function StepVisitDetails({
  providers,
  register,
  isDoctorVisit,
  showProviderSelect,
  onAddProvider,
  chiefComplaint,
  onChiefComplaintChange,
  notes,
  onNotesChange,
  tags,
  onTagsChange,
  tagInput,
  onTagInputChange,
  providerLabel = "Provider",
}: StepVisitDetailsProps) {
  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        Visit Details
      </p>

      {/* Provider */}
      {showProviderSelect && (
        <div className="space-y-0.5">
          <Label htmlFor="provider_id" className="text-xs">
            {providerLabel}
          </Label>
          {providers.length > 0 ? (
            <select
              id="provider_id"
              {...register("provider_id")}
              className="flex h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onChange={(e) => {
                if (e.target.value === "__add_new__") {
                  e.target.value = "";
                  onAddProvider();
                } else {
                  register("provider_id").onChange(e);
                }
              }}
            >
              <option value="">Select {providerLabel.toLowerCase()}...</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.speciality ? ` - ${p.speciality}` : ""}
                </option>
              ))}
              <option value="__add_new__">+ Add new provider...</option>
            </select>
          ) : (
            <div className="flex gap-1.5">
              <Input
                id="provider_id"
                {...register("provider_id")}
                placeholder={`e.g. Dr. Smith`}
                className="h-8 flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 px-2 text-xs"
                onClick={onAddProvider}
              >
                <Plus className="h-3 w-3" />
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Chief Complaint (doctor visit only) */}
      {isDoctorVisit && (
        <div className="space-y-0.5">
          <Label className="text-xs">Chief Complaint</Label>
          <Textarea
            rows={1}
            placeholder="Describe the main reason for the visit..."
            className="text-sm"
            value={chiefComplaint}
            onChange={(e) => onChiefComplaintChange(e.target.value)}
          />
        </div>
      )}

      {/* Diagnosis */}
      <div className="space-y-0.5">
        <Label htmlFor="diagnosis" className="text-xs">
          Diagnosis
        </Label>
        <Input
          id="diagnosis"
          {...register("diagnosis")}
          placeholder="Diagnosis if any"
          className="h-8"
        />
      </div>

      {/* Next Review Date */}
      <div className="space-y-0.5">
        <Label htmlFor="next_review_date" className="text-xs">
          Next Review Date
        </Label>
        <Input
          id="next_review_date"
          type="text"
          placeholder="DD-MM-YYYY"
          {...register("next_review_date")}
          className="h-8"
        />
      </div>

      {/* Notes (doctor visit) */}
      {isDoctorVisit && (
        <div className="space-y-0.5">
          <Label className="text-xs">Notes</Label>
          <Textarea
            rows={1}
            placeholder="Additional observations, advice..."
            className="text-sm"
            value={notes}
            onChange={(e) => onNotesChange(e.target.value)}
          />
        </div>
      )}

      {/* Tags */}
      <div className="space-y-1">
        <Label className="text-xs">Tags</Label>
        <input type="hidden" name="tags" value={JSON.stringify(tags.length > 0 ? tags : null)} />
        <div className="flex gap-2">
          <Input
            value={tagInput}
            onChange={(e) => onTagInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                const v = tagInput.trim();
                if (v && !tags.includes(v)) {
                  onTagsChange([...tags, v]);
                  onTagInputChange("");
                }
              }
            }}
            placeholder="Add tag, press Enter"
            className="h-8 flex-1"
          />
        </div>
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <Badge key={t} variant="secondary" className="gap-1 text-xs">
                {t}
                <button
                  type="button"
                  onClick={() => onTagsChange(tags.filter((x) => x !== t))}
                  className="hover:opacity-70"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
