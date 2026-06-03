import useSWR from "swr";
import { listProviders } from "@/lib/api/providers";
import { ProvidersContent } from "@/components/content/providers-content";
import { ErrorState } from "@/components/shared/error-state";
import { PageLoader } from "@/components/shared/page-loader";

export default function ProvidersPage() {
  const { data, error, mutate } = useSWR("providers", () => listProviders());
  if (error) return <ErrorState onRetry={() => mutate()} />;
  if (!data) return <PageLoader title="Providers" />;
  return <ProvidersContent providers={data} />;
}
