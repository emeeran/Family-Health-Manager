import { Skeleton } from "@/components/ui/skeleton";

interface PageLoaderProps {
  title?: string;
}

export function PageLoader({ title }: PageLoaderProps) {
  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      {title && <Skeleton className="h-7 w-48" />}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-36 rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-48 w-full rounded-lg" />
    </div>
  );
}
