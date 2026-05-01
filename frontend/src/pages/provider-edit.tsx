import useSWR, { mutate } from "swr";
import { useParams, useNavigate } from "react-router-dom";
import { getProvider } from "@/lib/api/providers";
import { updateProvider } from "@/lib/api/providers";
import { ProviderForm } from "@/components/providers/provider-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import type { ProviderUpdate } from "@/lib/types/provider";

export default function EditProviderPage() {
  const { providerId } = useParams<{ providerId: string }>();
  const navigate = useNavigate();

  const { data: provider } = useSWR(providerId ? `provider-edit-${providerId}` : null, async () => {
    return getProvider(providerId!);
  });

  function createAction(pid: string) {
    return async function (prevState: unknown, formData: FormData) {
      const data: ProviderUpdate = {
        name: (formData.get("name") as string) || null,
        speciality: (formData.get("speciality") as string) || null,
        phone: (formData.get("phone") as string) || null,
        address: (formData.get("address") as string) || null,
      };
      try {
        await updateProvider(pid, data);
        mutate(`provider-edit-${pid}`);
        mutate(`provider-${pid}`);
        navigate(`/providers/${pid}`);
        return null;
      } catch (e) {
        return { error: e instanceof Error ? e.message : "Failed to update provider" };
      }
    };
  }

  if (!provider || !providerId)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  const action = createAction(providerId);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to={`/providers/${providerId}`} className="hover:underline">
          {provider.name}
        </Link>
        <span>/</span>
        <h1 className="text-2xl font-bold text-foreground">Edit Provider</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Edit {provider.name}</CardTitle>
        </CardHeader>
        <CardContent>
          <ProviderForm action={action} provider={provider} />
        </CardContent>
      </Card>
    </div>
  );
}
