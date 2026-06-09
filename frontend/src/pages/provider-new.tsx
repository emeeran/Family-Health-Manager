import { useNavigate } from "react-router-dom";
import { createProvider } from "@/lib/api/providers";
import { ProviderForm } from "@/components/providers/provider-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import type { ProviderCreate } from "@/lib/types/provider";
import type { ProviderType } from "@/lib/types/enums";

export default function NewProviderPage() {
  const navigate = useNavigate();

  async function action(prevState: unknown, formData: FormData) {
    const data: ProviderCreate = {
      name: formData.get("name") as string,
      provider_type: (formData.get("provider_type") as ProviderType) || "doctor",
      speciality: (formData.get("speciality") as string) || null,
      phone: (formData.get("phone") as string) || null,
      address: (formData.get("address") as string) || null,
    };
    try {
      await createProvider(data);
      navigate("/providers");
      return null;
    } catch (e) {
      return { error: e instanceof Error ? e.message : "Failed to create provider" };
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Link to="/providers" className="text-sm text-muted-foreground hover:underline">
          Providers
        </Link>
        <span className="text-sm text-muted-foreground">/</span>
        <h1 className="text-2xl font-bold">New Provider</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Add Healthcare Provider</CardTitle>
        </CardHeader>
        <CardContent>
          <ProviderForm action={action} />
        </CardContent>
      </Card>
    </div>
  );
}
