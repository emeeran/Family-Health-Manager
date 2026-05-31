import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <Card className="shadow-none">
      <CardContent className="pt-4 pb-3 space-y-2">
        <Skeleton className="h-4 w-32" />
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton
            key={i}
            className="h-3 w-full"
            style={{ width: `${70 + Math.random() * 30}%` }}
          />
        ))}
      </CardContent>
    </Card>
  );
}

export function OverviewSkeleton() {
  return (
    <div className="space-y-3">
      {/* Profile card skeleton */}
      <Card className="shadow-none">
        <CardContent className="p-4 sm:p-5 space-y-4">
          <div className="flex items-center gap-5">
            <Skeleton className="h-14 w-14 rounded-2xl shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-3 w-24" />
            </div>
            <Skeleton className="h-[68px] w-[68px] rounded-full shrink-0" />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-lg bg-muted/40 px-3 py-2 space-y-1">
                <Skeleton className="h-5 w-8" />
                <Skeleton className="h-2 w-14" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      {/* Vitals skeleton */}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="shadow-none">
            <CardContent className="pt-3 pb-2 text-center space-y-1">
              <Skeleton className="h-5 w-12 mx-auto" />
              <Skeleton className="h-2 w-10 mx-auto" />
            </CardContent>
          </Card>
        ))}
      </div>
      {/* Medications skeleton */}
      <SkeletonCard lines={5} />
    </div>
  );
}

export function RecordsSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonCard lines={4} />
      <div className="grid gap-3 md:grid-cols-2">
        <SkeletonCard lines={6} />
        <SkeletonCard lines={8} />
      </div>
    </div>
  );
}

export function TimelineSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonCard lines={10} />
      <SkeletonCard lines={8} />
    </div>
  );
}

export function AiSkeleton() {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <SkeletonCard lines={4} />
        <SkeletonCard lines={4} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <SkeletonCard lines={3} />
        <SkeletonCard lines={5} />
      </div>
    </div>
  );
}
