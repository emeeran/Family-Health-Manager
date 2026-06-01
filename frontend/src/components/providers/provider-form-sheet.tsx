import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ProviderForm } from "@/components/providers/provider-form";
import { createProvider } from "@/lib/api/providers";
import { mutate } from "swr";
import type { ProviderCreate } from "@/lib/types/provider";

interface ProviderFormSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProviderFormSheet({ open, onOpenChange }: ProviderFormSheetProps) {
  async function action(prevState: unknown, formData: FormData) {
    const data: ProviderCreate = {
      name: formData.get("name") as string,
      speciality: (formData.get("speciality") as string) || null,
      phone: (formData.get("phone") as string) || null,
      address: (formData.get("address") as string) || null,
    };
    try {
      await createProvider(data);
      mutate("providers");
      mutate("dashboard");
      onOpenChange(false);
      return null;
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Failed to create provider" };
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>New Provider</SheetTitle>
          <SheetDescription>Add a healthcare provider.</SheetDescription>
        </SheetHeader>
        <div className="mt-4">
          <ProviderForm action={action} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
