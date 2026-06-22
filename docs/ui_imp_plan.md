# UI/UX Deep-Dive Implementation Plan

## Context

The Family Health Manager dashboard lacks visual hierarchy (flat `max-w-3xl` single-column), the record creation form is a 1,079-line monolith causing user overwhelm, and empty states across the app are generic and unhelpful. This plan addresses all three with incremental, independently-testable changes that preserve existing functionality.

---

## Shared Foundation: `Stepper` Component

**New file:** `frontend/src/components/ui/stepper.tsx`

Both the record wizard and onboarding polish need a step indicator. Extract the pattern already used in `onboarding-wizard.tsx` (lines 118-139) into a reusable component.

```typescript
interface StepperStep {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  optional?: boolean;
}

interface StepperProps {
  steps: StepperStep[];
  currentStep: number;
  completedSteps?: number[];
  onStepClick?: (step: number) => void;
  size?: "sm" | "default";
  className?: string;
}
```

- Horizontal circles connected by lines
- Active step: `bg-primary text-primary-foreground shadow-md`
- Completed: `bg-primary/10 text-primary` with checkmark icon
- Optional step: muted label
- Built with existing Tailwind utilities only, no external deps

---

## Area 1: Dashboard Redesign

### Problem
`home-content.tsx` renders all sections at equal visual weight in `max-w-3xl space-y-4`. The API already returns rich data (`DashboardSummary` has scores, risk_summary, medication_summary, vaccination_status, record_activity) but most is unused. `home.tsx` destructures the summary into narrow props instead of passing it through.

### Changes

**1. Modify `frontend/src/pages/home.tsx`**
- Replace the manual member/stats/records destructuring (lines 48-84) with a single `summary` prop pass
- `HomeContent` already calls `useDashboardSummary()` internally, so we just need to ensure it has access to the full `DashboardSummary`
- Keep redirect and error handling logic as-is

**2. Restructure `frontend/src/components/content/home-content.tsx`**
- Change `HomeContentProps` to accept `summary: DashboardSummary` instead of separate `members/stats/records`
- Change layout from `max-w-3xl mx-auto space-y-4` to:

```
max-w-5xl mx-auto
├── Zone A (full width)
│   ├── Greeting + date + member count (keep existing style)
│   ├── QuickActionsGrid (new — 4 action buttons in a row)
│   └── SmartEntryBar (existing)
├── Zone B (two-column: lg:grid-cols-[1fr_320px] gap-6)
│   ├── Left column (primary)
│   │   ├── AlertStrip (existing, conditional)
│   │   ├── ActivityFeed with section heading "Recent Activity" (existing, enhanced)
│   │   └── ContextualSection (existing)
│   └── Right column (secondary — "Insights" sidebar)
│       ├── FamilyStrip (reoriented to vertical stack on desktop)
│       ├── HealthOverviewCard (new — aggregate stats card)
│       └── Member health score cards (new, if scores exist)
```

- Update `HomeSkeleton` to match the new two-column proportions

**3. New: `frontend/src/components/home/quick-actions-grid.tsx`**
- 4 action buttons in a responsive row: Add Record, Add Reminder, Smart Entry, Chat
- Uses `Button variant="outline" size="sm"` with Lucide icons
- Wires to existing navigation/dialogs (same targets as `UniversalQuickAdd`)

**4. New: `frontend/src/components/home/health-overview-card.tsx`**
- Compact 2x2 stat grid inside a `Card size="sm"`:
  - Records this month (`record_activity.total_last_30_days`) with by-type breakdown as tiny badges
  - Vaccinations with overdue count highlighted red if > 0
  - Risk summary (high/moderate/low as colored dots)
  - Medication refills upcoming

**5. Modify `frontend/src/components/home/family-strip.tsx`**
- Accept optional `scores` prop (`MemberScore[]`)
- On desktop (inside sidebar column): render as vertical stack with mini `HealthScoreRing` beside each avatar
- On mobile: keep existing horizontal scroll behavior
- Add tooltip on score ring: "Score: 72/100 — Good"

**6. Modify `frontend/src/components/home/activity-feed.tsx`**
- Replace inline empty text (lines ~107-119) with the shared `EmptyState` component
- Add "Add your first record" action in the empty state

### Files touched
- `frontend/src/pages/home.tsx` — simplify prop passing
- `frontend/src/components/content/home-content.tsx` — restructure layout
- `frontend/src/components/home/family-strip.tsx` — add scores, responsive reorientation
- `frontend/src/components/home/activity-feed.tsx` — improve empty state
- **New:** `frontend/src/components/home/quick-actions-grid.tsx`
- **New:** `frontend/src/components/home/health-overview-card.tsx`

---

## Area 2: Record Form Wizard

### Problem
`record-form.tsx` is 1,079 lines mixing 20+ state variables, file upload UI, type-specific fields, medication sync dialogs, and form submission in one component. The form is rendered as a flat page with all fields visible simultaneously.

### Strategy
**Extract, don't rewrite.** Create a parallel `RecordFormWizard` component that wraps the same state and form logic but renders it through step components. The existing `RecordForm` stays untouched for record editing and as a fallback.

### Wizard Steps

| Step | Title | Contents | Source lines |
|------|-------|----------|-------------|
| 1 | Record Type & Files | Type selector, date, file upload area | ~421-701 |
| 2 | Visit Details | Provider (+ inline add), chief complaint, diagnosis, next review, tags | ~703-916, 919-956 |
| 3 | Clinical Data | TypeSpecificFields, dynamic tables, notes, clinical data textarea | ~828-898, 958-982 |
| 4 | Review & Save | Read-only summary of all data, file status, medication preview, save button | New |

Navigation: non-linear (click stepper to jump), save only on step 4, step 1 auto-skipped if `defaultType` is set.

### New files (inside `frontend/src/components/records/wizard/`)

**1. `record-form-wizard.tsx`** — Orchestrator
- Same `RecordFormProps` interface as current `RecordForm`
- Manages `currentStep` state and `Stepper` rendering
- All hooks stay here: `useActionState`, `useForm`, `useFileExtraction`, all `useState`
- Renders `<form>` wrapper with step components conditionally
- Includes the medication confirmation + sync dialogs (unchanged logic)

**2. `step-type-selection.tsx`** — Presentational
- Props: `recordType`, `onRecordTypeChange`, `recordDate`, `onRecordDateChange`, `uploadSection` (React node from parent)
- Renders: type select, date input, file upload/extraction area

**3. `step-visit-details.tsx`** — Presentational
- Props: provider fields, chief complaint, diagnosis, next review date, tags, errors, `isDoctorVisit`, `onAddProvider` callback
- Renders: provider select + add provider trigger, conditional complaint field, diagnosis, review date, tags input
- Add Provider dialog stays in wizard parent; this step just triggers it via callback

**4. `step-clinical-data.tsx`** — Presentational
- Props: `config`, `customValues`, `tableData`, `notes`, auto-fill batches, callbacks
- Renders: `TypeSpecificFields`, `DynamicTable`, notes textarea, clinical data fallback textarea

**5. `step-review.tsx`** — Presentational
- Props: all form values in read-only mode, `isPending`, `isEditing`, `onSubmit`, `onReset`
- Renders: summary card of all entered data, file attachment status, medication preview if prescriptions detected, save button

### Modify `frontend/src/pages/record-new.tsx`
- Import `RecordFormWizard` instead of `RecordForm`
- Same props — drop-in replacement
- Add a small "Switch to classic form" link that toggles to `RecordForm` (stored in localStorage preference)

### Files NOT changed
- `record-form.tsx` — untouched, used for editing
- `record-edit.tsx` — continues using `RecordForm`
- `quick-add-record-dialog.tsx` — independent, bypasses both
- `smart-entry.tsx` — independent entry path
- All quick forms (`quick-blood-glucose-form.tsx`, etc.) — independent

### Files touched
- `frontend/src/pages/record-new.tsx` — swap to wizard
- **New:** `frontend/src/components/records/wizard/record-form-wizard.tsx`
- **New:** `frontend/src/components/records/wizard/step-type-selection.tsx`
- **New:** `frontend/src/components/records/wizard/step-visit-details.tsx`
- **New:** `frontend/src/components/records/wizard/step-clinical-data.tsx`
- **New:** `frontend/src/components/records/wizard/step-review.tsx`

---

## Area 3: Empty States & Onboarding Polish

### Problem
`EmptyState` (28 lines) is one generic component used in 8 locations with manually-constructed props. No contextual guidance, no illustrations, no differentiation between "first use" and "filter empty". Onboarding wizard lacks progress bar, optional step affordance is just button text.

### Changes

**1. Enhance `frontend/src/components/shared/empty-state.tsx`**
- Add optional `variant` prop: `"default" | "compact" | "illustrated"`
- Add optional `illustration` prop as alternative to `icon`
- "compact": smaller padding (`py-8`), used for inline empty states inside panels
- "illustrated": larger padding (`py-20`), illustration above title, used for full-page empty states
- **Fully backward compatible** — existing callers with `icon/title/description/action` work unchanged

**2. New: `frontend/src/components/shared/empty-state-illustrations.tsx`**
- Simple SVG illustrations (~20-30 lines each) for: records, members, providers, reminders, timeline
- Themed with `currentColor` for automatic dark mode compatibility
- Each exported as a named component: `RecordsEmptyIllustration`, `MembersEmptyIllustration`, etc.

**3. New: `frontend/src/components/shared/contextual-empty-state.tsx`**
- Wraps enhanced `EmptyState` with preset configurations:

```typescript
type EmptyStateVariant = "no-data" | "filtered" | "error";
type EmptyStateContext = "records" | "members" | "providers" | "reminders" | "timeline" | "provider-assignments";

interface ContextualEmptyStateProps {
  variant: EmptyStateVariant;
  context: EmptyStateContext;
  // Optional overrides for any preset field
  title?: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}
```

- Maps each `variant × context` combination to pre-built illustration + title + description + action
- Example presets:
  - `no-data + records` → clipboard illustration + "No records yet" + "Start by adding a health record for your family members." + "Add First Record" button
  - `filtered + records` → filter icon + "No matching records" + "Try adjusting your filters or date range." + "Clear Filters" link
  - `no-data + members` → family illustration + "No family members" + "Add your first family member to begin tracking health records." + "Add Member" button

**4. Migrate content files (one at a time, independently testable)**

Each migration replaces manual `EmptyState` construction with `ContextualEmptyState`:

| File | Current | Replacement |
|------|---------|-------------|
| `content/records-list-content.tsx` (line 221) | Manual icon/title/description | `<ContextualEmptyState variant={records.length === 0 ? "no-data" : "filtered"} context="records" />` |
| `content/members-content.tsx` (line 202) | Manual | `<ContextualEmptyState variant="no-data" context="members" />` |
| `content/providers-content.tsx` (line 106) | Manual | `<ContextualEmptyState variant="no-data" context="providers" />` |
| `content/reminders-content.tsx` (line 123) | Manual | `<ContextualEmptyState variant={reminders.length === 0 ? "no-data" : "filtered"} context="reminders" />` |
| `content/household-records-content.tsx` (line 112) | Manual | `<ContextualEmptyState variant={records.length === 0 ? "no-data" : "filtered"} context="records" />` |
| `content/timeline-content.tsx` (line 445) | Manual | `<ContextualEmptyState variant="no-data" context="timeline" />` |
| `content/member-providers-content.tsx` (line 142) | Manual | `<ContextualEmptyState variant="no-data" context="provider-assignments" />` |

**5. Polish `frontend/src/components/content/onboarding-wizard.tsx`**
- Replace custom step indicator (lines 118-139) with shared `<Stepper>` component
- Add `<Progress value={(step / (STEPS.length - 1)) * 100} />` below stepper
- Step 2 (Provider): Add `<Badge variant="outline">optional</Badge>` next to "Provider" title
- Add explicit "Skip for now" as a `Button variant="ghost"` below the form fields (not just button text change)
- Add tooltip on skip: "You can add providers later from the Providers page"
- Add `animate-fade-in-up` class to step content wrapper for smooth transitions
- Add step descriptions (already partially present in `CardDescription`, just ensure consistency)

### Files touched
- `frontend/src/components/shared/empty-state.tsx` — add variant/illustration props
- `frontend/src/components/content/onboarding-wizard.tsx` — polish with stepper, progress, skip
- 7 content files — swap to `ContextualEmptyState` (each independent)
- **New:** `frontend/src/components/shared/empty-state-illustrations.tsx`
- **New:** `frontend/src/components/shared/contextual-empty-state.tsx`

---

## Implementation Order

```
Phase 1 — Foundation (no user-facing changes)
  1. stepper.tsx
  2. empty-state.tsx enhancement (backward compatible)
  3. empty-state-illustrations.tsx

Phase 2 — Area 3: Empty States (quick wins, low risk)
  4. contextual-empty-state.tsx
  5. Migrate 7 content files (one at a time)

Phase 3 — Area 1: Dashboard (medium effort)
  6. quick-actions-grid.tsx
  7. health-overview-card.tsx
  8. Simplify home.tsx props
  9. Restructure home-content.tsx layout
  10. Update family-strip.tsx (scores + responsive)
  11. Update activity-feed.tsx empty state

Phase 4 — Area 2: Record Wizard (highest effort)
  12. step-type-selection.tsx
  13. step-visit-details.tsx
  14. step-clinical-data.tsx
  15. step-review.tsx
  16. record-form-wizard.tsx (orchestrator)
  17. Modify record-new.tsx to use wizard
  18. Polish onboarding-wizard.tsx (uses stepper from phase 1)

Phase 5 — Polish
  19. Update HomeSkeleton for new layout
  20. Cross-browser / mobile testing
```

## Verification

### Per-area testing
- **Area 1:** Load dashboard → verify two-column layout on desktop, single column on mobile → verify quick actions navigate correctly → verify health overview card shows real data → verify family strip shows scores with tooltips
- **Area 2:** Create record via wizard (all 4 steps) → create doctor visit with prescriptions → verify medication sync dialog still appears → edit existing record (should still use classic form) → verify quick forms still work from quick-add dialog
- **Area 3:** Load each empty page (no data) → verify contextual illustration + guidance appears → filter to empty → verify "no matching" variant → complete onboarding → verify stepper, progress bar, skip button, step transitions

### Commands
```bash
cd frontend && npx tsc --noEmit          # Type check
cd backend && uv run pytest              # Backend unchanged, but verify
cd frontend && npm run build             # Production build check
```

### Manual checks
- Dark mode rendering across all three areas
- Mobile viewport (375px, 768px, 1024px)
- Keyboard navigation through wizard steps
- Screen reader announcement of stepper progress
