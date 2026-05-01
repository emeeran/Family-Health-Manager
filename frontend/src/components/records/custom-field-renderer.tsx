import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { FieldDef } from "@/lib/record-type-configs";

interface CustomFieldRendererProps {
  field: FieldDef;
  value: string;
  onChange: (key: string, value: string) => void;
  error?: string;
  className?: string;
}

export function CustomFieldRenderer({
  field,
  value,
  onChange,
  error,
  className,
}: CustomFieldRendererProps) {
  const id = `cf-${field.key}`;

  const inputProps: Record<string, string> = {};
  if (field.step) inputProps.step = field.step;
  if (field.min !== undefined) inputProps.min = field.min;
  if (field.max !== undefined) inputProps.max = field.max;

  return (
    <div className={`space-y-1 ${className || ""}`}>
      <div className="flex items-baseline justify-between">
        <Label htmlFor={id}>
          {field.label}
          {field.required && <span className="text-destructive ml-0.5">*</span>}
        </Label>
        {field.helpText && <span className="text-xs text-muted-foreground">{field.helpText}</span>}
      </div>

      {field.type === "select" ? (
        <Select value={value || ""} onValueChange={(v) => onChange(field.key, v ?? "")}>
          <SelectTrigger id={id} className="w-full">
            <SelectValue placeholder={`Select ${field.label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {field.options?.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : field.type === "textarea" ? (
        <Textarea
          id={id}
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          rows={2}
        />
      ) : (
        <Input
          id={id}
          type={field.type}
          value={value}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          {...inputProps}
        />
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
