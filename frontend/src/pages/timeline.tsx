import { useState, useCallback } from "react";
import useSWR from "swr";
import { useParams } from "react-router-dom";
import { getTimeline } from "@/lib/api/records";
import { getMember } from "@/lib/api/members";
import { TimelineContent } from "@/app/(app)/members/[memberId]/timeline/timeline-content";
import type { RecordType } from "@/lib/types/enums";
import type { HealthRecordResponse } from "@/lib/types/health-record";
import { ErrorState } from "@/components/shared/error-state";

export default function TimelinePage() {
  const { memberId } = useParams<{ memberId: string }>();
  const [allItems, setAllItems] = useState<HealthRecordResponse[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [_initialized, setInitialized] = useState(false);
  const [filterType, setFilterType] = useState<RecordType | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Fetch member
  const {
    data: member,
    error: memberError,
    mutate: mutateMember,
  } = useSWR(memberId ? ["member", memberId] : null, async ([, mid]) => {
    return getMember(mid);
  });

  // Fetch initial timeline
  const {
    isLoading,
    error: timelineError,
    mutate: mutateTimeline,
  } = useSWR(memberId ? ["timeline-init", memberId, filterType] : null, async ([, mid, fType]) => {
    const params: Record<string, string | undefined> = {};
    if (fType) params.record_type = fType;
    const res = await getTimeline(mid, Object.keys(params).length > 0 ? params : undefined);
    setAllItems(res.items);
    setCursor(res.next_cursor);
    setHasMore(res.has_more);
    setInitialized(true);
    return res;
  });

  // Load more
  const handleLoadMore = useCallback(async () => {
    if (!memberId || !cursor) return;
    setLoadingMore(true);
    try {
      const params: Record<string, string | undefined> = { cursor };
      if (filterType) params.record_type = filterType;
      const res = await getTimeline(memberId, params);
      setAllItems((prev) => [...prev, ...res.items]);
      setCursor(res.next_cursor);
      setHasMore(res.has_more);
    } finally {
      setLoadingMore(false);
    }
  }, [memberId, cursor, filterType]);

  // Filter change — reset and refetch
  const handleFilterChange = useCallback((recordType: RecordType | null) => {
    setFilterType(recordType);
    setAllItems([]);
    setCursor(null);
    setHasMore(false);
    setInitialized(false);
  }, []);

  if (memberError || timelineError) {
    return (
      <ErrorState
        onRetry={() => {
          mutateMember();
          mutateTimeline();
        }}
      />
    );
  }

  if (!member || isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <TimelineContent
      items={allItems}
      member={member}
      hasMore={hasMore}
      onLoadMore={handleLoadMore}
      loadingMore={loadingMore}
      onFilterChange={handleFilterChange}
      activeFilter={filterType}
    />
  );
}
