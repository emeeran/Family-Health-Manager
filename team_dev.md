# Production Readiness Audit & Remediation Plan

**Goal**: Eliminate dead code, fix duplication, resolve type safety issues, and verify build integrity — no speculative refactoring.

---

## Workstream 1: Dead Code Elimination

### 1.1 Delete orphaned content files

| File | Lines | Reason |
|------|-------|--------|
| `src/components/content/conversations-content.tsx` | ~300 | Replaced by unified chat. Zero imports. |
| `src/components/content/notifications-content.tsx` | ~190 | Never imported — notifications page has its own inline impl. |

### 1.2 Remove `conversation-detail.tsx` and redirect its route

**Delete**: `src/pages/conversation-detail.tsx` (~530 lines)

**Modify**: `src/router.tsx`
- Remove lazy import: `const ConversationDetailPage = lazy(...)`
- Replace route element with redirect loader:
```tsx
{
  path: "conversations/:conversationId",
  loader: ({ params }) => { throw redirect(`/conversations?conversationId=${params.conversationId}`); },
},
```

**Also remove** leftover lazy imports for pages already converted to redirect loaders:
- `MemberRecordsPage`, `TimelinePage`, `LabRecordsPage`, `MemberProvidersPage` — their routes are already loaders but imports still sit at top of file.

### 1.3 Verify
```bash
grep -r "conversations-content\|notifications-content" src/
grep -r "conversation-detail" src/ --include="*.ts" --include="*.tsx"
npx tsc --noEmit && npx vite build
```

**Lines removed**: ~1,020

---

## Workstream 2: Deduplication (depends on WS1)

### 2.1 Extract shared lazy MarkdownRenderer

**Create**: `src/components/shared/lazy-markdown.tsx`
```tsx
import { lazy } from "react";
export const MarkdownRenderer = lazy(async () => {
  const [{ default: ReactMarkdown }, { default: remarkGfm }] = await Promise.all([
    import("react-markdown"),
    import("remark-gfm"),
  ]);
  return {
    default: ({ content }: { content: string }) => (
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    ),
  };
});
```

**Modify**: `src/components/conversations/chat-area.tsx`
- Delete local `MarkdownRenderer` lazy block (lines 21-31)
- Add import: `import { MarkdownRenderer } from "@/components/shared/lazy-markdown";`
- Keep the `Suspense` wrapping as-is — that's usage-site specific

Note: `conversation-detail.tsx` duplicate is eliminated by WS1 (file deleted).

### 2.2 Consolidate `relativeTime` → `formatRelativeTime`

Canonical: `src/lib/utils.ts` — `formatRelativeTime()` (handles past + future dates)

**Modify**: `src/pages/notifications.tsx`
- Delete local `relativeTime` function (lines 19-31)
- Add import: `import { formatRelativeTime } from "@/lib/utils";`
- Replace all `relativeTime(...)` calls → `formatRelativeTime(...)`

**Modify**: `src/components/conversations/conversation-sidebar-panel.tsx`
- Delete local `relativeTime` function (lines 13-25)
- Merge into existing `import { cn } from "@/lib/utils"` → `import { cn, formatRelativeTime } from "@/lib/utils"`
- Replace all `relativeTime(...)` calls → `formatRelativeTime(...)`
- Note: sidebar currently uses short form ("3m", "now"). After switch, displays "3m ago", "Just now" — acceptable standardization.

Note: `notifications-content.tsx` copy is eliminated by WS1 (file deleted).

### 2.3 Verify
```bash
grep -rn "function relativeTime" src/
npx tsc --noEmit && npx vite build
```

---

## Workstream 3: Type Safety Fixes (independent, parallel with WS1)

### 3.1 Fix `as any[]` in dashboard

**Root cause**: Backend returns 4-field reminder objects but frontend types expect full `ReminderResponse` (9+ fields). The template at `dashboard-content.tsx:430` accesses `reminder.family_member_id` — so the type needs that field too.

**Modify**: `src/components/content/dashboard-content.tsx`
- Add a `DashboardReminder` type with the fields actually used:
  - `id: string`, `title: string`, `start_datetime: string | null`, `reminder_type: string`, `family_member_id: string | null`
- Change `DashboardStats.upcomingReminders` from `ReminderResponse[]` to `DashboardReminder[]`
- Remove `ReminderResponse` import if no longer used

**Modify**: `src/pages/dashboard.tsx`
- Change `as any[]` → remove cast entirely (types now match)

### 3.2 Fix Recharts `any` types

**Modify**: `src/components/members/chronic-condition-charts.tsx`
- Replace lines 2-3:
```tsx
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RechartsFormatter = (value: any, name: any, props: any) => any;
```
- With a tighter type matching actual usage:
```tsx
// Recharts Tooltip formatter callback lacks precise types
type RechartsFormatter = (value: string | number, name: string, props: Record<string, unknown>) => [string, string];
```
- The inline arrow at line 23 already has the correct signature; the cast just needs to match.

### 3.3 Verify
```bash
grep -rn "as any" src/ --include="*.tsx" --include="*.ts"
npx tsc --noEmit && npx vite build
```

---

## Workstream 4: Build & Smoke Verification (after all WS complete)

### 4.1 Automated checks
```bash
cd frontend
npx tsc --noEmit          # type check
npx eslint src/ --max-warnings 0  # lint
npx vite build             # production build
```

### 4.2 Dangling reference scan
```bash
grep -r "conversations-content\|notifications-content\|conversation-detail" src/
grep -rn "function relativeTime" src/
grep -rn "as any" src/ --include="*.tsx" --include="*.ts"
```

### 4.3 Smoke tests (manual or Playwright)
1. `/conversations` — sidebar loads, mode toggle works, chat input works
2. `/conversations/some-uuid` → redirects to `/conversations?conversationId=some-uuid`
3. Markdown renders in AI response (bold, lists)
4. `/notifications` — timestamps display correctly
5. `/dashboard` — reminders section renders without errors
6. Member detail — chronic condition glucose chart renders tooltips

### 4.4 Bundle comparison
- Before: capture `npx vite build` output
- After: confirm `conversation-detail` chunk gone, ~20-30KB gzipped saved

---

## Dependency Graph

```
WS1 (Dead Code) ──────┐
                       ├──> WS4 (Verification)
WS2 (Dedup) ──────────┤
  needs WS1 done first │
                       │
WS3 (Type Safety) ────┘
  fully independent
```

**Execution**: WS1 + WS3 in parallel → WS2 → WS4

---

## Out of Scope (with rationale)

| Item | Reason |
|------|--------|
| Split large components (record-form 1.9K lines etc.) | Speculative refactoring — working code, not broken |
| Frontend component tests | Enhancement, not cleanup |
| Backend router consolidation | All routers are active and mounted |
| Untracked new files (ai/, member_detail, tabs/) | Active feature development, not cleanup |
| agy_report_300526.md | Not code — user decision on inclusion |
| Performance/load testing | Separate sprint |
