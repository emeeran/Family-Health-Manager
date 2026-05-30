import useSWR from "swr";
import { listProviders } from "@/lib/api/providers";
import { ProvidersContent } from "@/components/content/providers-content";
import { ErrorState } from "@/components/shared/error-state";

export default function ProvidersPage() {
  const {
    data: providers,
    error,
    mutate,
  } = useSWR("providers", async () => {
    return listProviders();
  });
  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!providers)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <ProvidersContent providers={providers} />;
}
