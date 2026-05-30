import useSWR from "swr";
import { useParams } from "react-router-dom";
import { getProvider, getProviderMembers } from "@/lib/api/providers";
import { ProviderDetailContent } from "@/components/content/provider-detail-content";
import { ErrorState } from "@/components/shared/error-state";

export default function ProviderDetailPage() {
  const { providerId } = useParams<{ providerId: string }>();
  const { data, error, mutate } = useSWR(providerId ? `provider-${providerId}` : null, async () => {
    const [provider, members] = await Promise.all([
      getProvider(providerId!),
      getProviderMembers(providerId!).catch(() => []),
    ]);
    return { provider, members };
  });
  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data)
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  return <ProviderDetailContent provider={data.provider} assignedMembers={data.members} />;
}
