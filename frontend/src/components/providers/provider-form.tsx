import { useActionState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ProviderResponse } from "@/lib/types/provider";

const providerSchema = z.object({
  name: z.string().min(1, "Provider name is required").max(100),
  speciality: z.string().max(100).optional(),
  phone: z.string().max(50).optional(),
  address: z.string().max(500).optional(),
});

type ProviderFormValues = z.infer<typeof providerSchema>;

interface ProviderFormProps {
  action: (prevState: unknown, formData: FormData) => Promise<unknown>;
  provider?: ProviderResponse;
}

export function ProviderForm({ action, provider }: ProviderFormProps) {
  const [state, formAction, isPending] = useActionState<unknown, FormData>(action, null);

  const {
    register,
    reset,
    formState: { errors },
  } = useForm<ProviderFormValues>({
    resolver: zodResolver(providerSchema),
    defaultValues: { name: "", speciality: "", phone: "", address: "" },
  });

  // Populate form when provider data arrives
  useEffect(() => {
    if (provider) {
      reset({
        name: provider.name,
        speciality: provider.speciality ?? "",
        phone: provider.phone ?? "",
        address: provider.address ?? "",
      });
    }
  }, [provider, reset]);

  return (
    <form action={formAction} className="space-y-4 max-w-2xl">
      {Boolean(
        state && typeof state === "object" && "error" in (state as Record<string, unknown>)
      ) && (
        <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {String((state as Record<string, unknown>).error ?? "Unknown error")}
        </div>
      )}

      <div className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Provider Details
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="name" className="text-xs">
              Name
            </Label>
            <Input
              id="name"
              {...register("name")}
              placeholder="e.g., Dr. Jane Smith"
              className="h-9"
            />
            {errors.name && <p className="text-[11px] text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="speciality" className="text-xs">
              Speciality
            </Label>
            <Input
              id="speciality"
              {...register("speciality")}
              placeholder="e.g., Cardiology"
              className="h-9"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="phone" className="text-xs">
              Phone
            </Label>
            <Input
              id="phone"
              type="tel"
              {...register("phone")}
              placeholder="(555) 123-4567"
              className="h-9"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="address" className="text-xs">
              Address
            </Label>
            <Textarea
              id="address"
              {...register("address")}
              rows={2}
              placeholder="Full address"
              className="text-sm min-h-[60px]"
            />
          </div>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <Button type="submit" disabled={isPending} size="sm">
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          {isPending ? "Saving..." : provider ? "Update Provider" : "Add Provider"}
        </Button>
      </div>
    </form>
  );
}
