# ADR-003: Cursor-based Pagination for List Endpoints

## Status: Accepted

## Context

The application requires pagination on all list endpoints (NFR-001, SPEC.md Section 4.2):
- Health records timeline (potentially hundreds per member)
- Provider lists
- Reminder lists
- Notification lists
- Conversation message history
- Audit logs

Key requirements:
- Consistent pagination contract across all endpoints
- Handle real-time data (records added while paginating)
- Prevent offset drift (items appearing/disappearing between pages)
- Performance: ≤500ms response time for 95th percentile (NFR-001)

## Decision

Use **cursor-based pagination** (keyset pagination) for all list endpoints.

**Contract:**

**Request query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | null | Opaque cursor from previous response |
| `limit` | integer | 20 | Items per page (max 100) |

**Response envelope:**
```json
{
  "items": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6IjEyMyIsInJlY29yZF9kYXRlIjoiMjAyNC0wMS0xNSJ9",
    "has_more": true,
    "total_count": 150
  }
}
```

**Cursor encoding:**
- Cursor is base64-encoded JSON containing sort key values
- Example: `{"id": "123", "record_date": "2024-01-15"}`
- Opaque to client — no parsing required

**SQL pattern:**
```sql
SELECT * FROM health_records
WHERE family_member_id = :member_id
  AND is_deleted = false
  AND (record_date, id) < (:cursor_date, :cursor_id)
ORDER BY record_date DESC, id DESC
LIMIT :limit + 1
```

**Sort order:**
- Primary: `record_date DESC` (newest first)
- Secondary: `id DESC` (tie-breaker for same-date records)

## Consequences

**Positive:**
- **No offset drift** — New records don't cause duplicates or skipped items
- **Consistent performance** — Query time independent of page depth
- **Index-friendly** — Uses composite index on (date, id)
- **Scalable** — Works efficiently with millions of records

**Negative:**
- **Cannot jump to page** — Client must paginate sequentially (no "go to page 10")
- **Cursor opacity** — Clients cannot construct cursors manually
- **Total count cost** — Separate COUNT query required for total_count
- **Complex sort keys** — Multiple sort columns require tuple comparison

**Mitigations:**
- Page jumping: Not required for use case (users view recent records first)
- Cursor construction: Document cursor as opaque string in API docs
- Total count: Optional optimization — cache count or omit for large datasets
- Tuple comparison: SQLAlchemy supports `tuple_()` for multi-column comparison

**Performance characteristics:**
- First page: ~10-50ms (index scan)
- Deep pages: ~10-50ms (same — cursor seeks directly to position)
- Count query: ~5-20ms (indexed count)
- Total: Well under 500ms NFR target

## Alternatives Considered

### Offset-based pagination (LIMIT/OFFSET)
- **Pros:** Simple, supports "jump to page N", intuitive API
- **Cons:** O(N) performance degradation with depth, offset drift on inserts/deletes
- **Verdict:** Rejected — performance degrades linearly with offset

### Seek-based pagination (single key)
- **Pros:** Simpler cursor (single value), good performance
- **Cons:** Requires unique monotonic key, doesn't work with non-unique sort columns
- **Verdict:** Considered — but record_date is not unique, requires composite key

### Relay-style cursor (GraphQL)
- **Pros:** Standard for GraphQL, base64-encoded opaque cursors
- **Cons:** Verbose for REST API, `hasPreviousPage` not needed for our use case
- **Verdict:** Adapted simplified version — dropped connection/edge abstraction

### Time-based pagination
- **Pros:** Natural for health records (filter by date ranges)
- **Cons:** Doesn't handle multiple records per day well
- **Verdict:** Incorporated as optional `date_from`/`date_to` filters alongside cursor

### Keyset pagination without total count
- **Pros:** Single query, fastest possible
- **Cons:** Client doesn't know total pages
- **Verdict:** Rejected — total_count required for progress indicators

**Implementation notes:**

```python
# app/core/deps.py
class PaginationParams:
    def __init__(self, cursor: str | None = None, limit: int = 20):
        self.cursor = self._decode_cursor(cursor)
        self.limit = min(limit, 100)  # Cap at 100
    
    def _decode_cursor(self, cursor: str | None) -> dict | None:
        if not cursor:
            return None
        return json.loads(base64.b64decode(cursor))

# app/services/health_record_service.py
def list_records(self, member_id: UUID, pagination: PaginationParams):
    query = select(HealthRecord).where(
        HealthRecord.family_member_id == member_id,
        HealthRecord.is_deleted == False
    )
    
    if pagination.cursor:
        # Tuple comparison for composite key
        query = query.where(
            tuple_(HealthRecord.record_date, HealthRecord.id) < 
            (pagination.cursor['record_date'], pagination.cursor['id'])
        )
    
    query = query.order_by(
        HealthRecord.record_date.desc(),
        HealthRecord.id.desc()
    ).limit(pagination.limit + 1)
    
    results = await db.execute(query)
    records = results.scalars().all()
    
    has_more = len(records) > pagination.limit
    items = records[:pagination.limit]
    next_cursor = self._encode_cursor(items[-1]) if has_more else None
    
    return PaginatedResult(items=items, next_cursor=next_cursor, has_more=has_more)
```

---

**Date:** 2026-04-02  
**Author:** Principal Engineer (AI)  
**Reviewers:** Specification Review Gate
