# UI/UX Implementation Task List

## Dependency Graph

```
Phase 1 — Foundation (no blockers, can run in parallel)
  #2  Stepper component
  #3  EmptyState enhancement
  #4  SVG illustrations
  #7  QuickActionsGrid
  #8  HealthOverviewCard
  #9  Simplify home.tsx
  #13 Wizard Step 1
  #14 Wizard Step 2
  #15 Wizard Step 3
  #16 Wizard Step 4

Phase 2 — Integration (blocked by Phase 1)
  #5  ContextualEmptyState        ← blocked by #3, #4
  #10 Dashboard restructure       ← blocked by #7, #8, #9
  #17 RecordFormWizard            ← blocked by #2, #13, #14, #15, #16
  #19 Onboarding polish           ← blocked by #2

Phase 3 — Final wiring (blocked by Phase 2)
  #6  Migrate 7 content files     ← blocked by #5
  #11 Family strip scores         ← blocked by #10
  #12 Activity feed empty state   ← blocked by #10
  #18 Wire wizard to page         ← blocked by #17
  #20 Update HomeSkeleton         ← blocked by #10
```

---

## Tasks

### #2 — Create shared Stepper UI component
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/ui/stepper.tsx`

Extract the step indicator pattern from `onboarding-wizard.tsx` (lines 118-139) into a reusable component.

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
- Completed step: `bg-primary/10 text-primary` with `CheckCircle2` icon
- Optional step: muted label
- Tailwind only, no external deps
- Shared dependency for #17 (wizard) and #19 (onboarding polish)

---

### #3 — Enhance EmptyState with variant and illustration support
- **Status:** pending
- **Blocked by:** none
- **Modify:** `frontend/src/components/shared/empty-state.tsx` (currently 28 lines)

Add to `EmptyStateProps`:
- `variant?: "default" | "compact" | "illustrated"` — controls padding and layout
- `illustration?: React.ReactNode` — alternative to `icon`, rendered larger

Variant behavior:
- `"default"` — current behavior, `py-16`
- `"compact"` — `py-8`, smaller icon area, for inline panel empty states
- `"illustrated"` — `py-20`, illustration rendered at larger size, for full-page empty states

**Must be fully backward compatible.** Existing callers passing `icon/title/description/action` continue to work unchanged.

---

### #4 — Create empty state SVG illustrations
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/shared/empty-state-illustrations.tsx`

Simple SVG illustration components (~20-30 lines each), themed with `currentColor` for automatic dark mode compatibility.

Export named components:
- `RecordsEmptyIllustration` — clipboard with pulse line
- `MembersEmptyIllustration` — family silhouettes
- `ProvidersEmptyIllustration` — stethoscope
- `RemindersEmptyIllustration` — calendar with clock
- `TimelineEmptyIllustration` — timeline dots with connecting line

Each accepts `className?: string` prop. Visually distinct, recognizable at 64×64 and 96×96 sizes.

---

### #5 — Create ContextualEmptyState wrapper component
- **Status:** pending
- **Blocked by:** #3, #4
- **New file:** `frontend/src/components/shared/contextual-empty-state.tsx`

Wraps enhanced `EmptyState` with preset configurations:

```typescript
type EmptyStateVariant = "no-data" | "filtered" | "error";
type EmptyStateContext = "records" | "members" | "providers" | "reminders" | "timeline" | "provider-assignments";

interface ContextualEmptyStateProps {
  variant: EmptyStateVariant;
  context: EmptyStateContext;
  title?: string;          // override preset
  description?: string;    // override preset
  action?: React.ReactNode; // override preset
  className?: string;
}
```

Preset mapping (variant × context):

| Context | `no-data` | `filtered` | `error` |
|---------|-----------|------------|---------|
| **records** | RecordsEmptyIllustration + "No records yet" + "Start by adding a health record for your family members." + "Add First Record" button | "No matching records" + "Try adjusting your filters or date range." + "Clear Filters" link | "Failed to load records" + "Something went wrong. Please try again." + "Retry" button |
| **members** | MembersEmptyIllustration + "No family members" + "Add your first family member to begin tracking health records." + "Add Member" button | "No matching members" + "Try adjusting your search." | "Failed to load members" + retry |
| **providers** | ProvidersEmptyIllustration + "No healthcare providers" + "Add a provider to associate with health records." + "Add Provider" button | "No matching providers" + "Try adjusting your search." | "Failed to load providers" + retry |
| **reminders** | RemindersEmptyIllustration + "No reminders" + "Set up medication or appointment reminders for your family." + "Add Reminder" button | "No matching reminders" + "Try adjusting your status filter." | "Failed to load reminders" + retry |
| **timeline** | TimelineEmptyIllustration + "No timeline entries" + "Health records will appear here as you add them." | "No entries in this range" + "Try selecting a different time period." | "Failed to load timeline" + retry |
| **provider-assignments** | "No providers assigned" + "Link a provider to this member's records." + "Assign Provider" button | "No matching providers" | "Failed to load" + retry |

---

### #6 — Migrate 7 content files to ContextualEmptyState
- **Status:** pending
- **Blocked by:** #5
- **Modify:** 7 content files (each independent)

For each file:
1. Replace `import { EmptyState }` with `import { ContextualEmptyState }`
2. Replace manual `EmptyState` construction with `ContextualEmptyState`

| File | Line | Replacement |
|------|------|-------------|
| `content/records-list-content.tsx` | 221 | `<ContextualEmptyState variant={records.length === 0 ? "no-data" : "filtered"} context="records" />` |
| `content/members-content.tsx` | 202 | `<ContextualEmptyState variant="no-data" context="members" />` |
| `content/providers-content.tsx` | 106 | `<ContextualEmptyState variant="no-data" context="providers" />` |
| `content/reminders-content.tsx` | 123 | `<ContextualEmptyState variant={reminders.length === 0 ? "no-data" : "filtered"} context="reminders" />` |
| `content/household-records-content.tsx` | 112 | `<ContextualEmptyState variant={records.length === 0 ? "no-data" : "filtered"} context="records" />` |
| `content/timeline-content.tsx` | 445 | `<ContextualEmptyState variant="no-data" context="timeline" />` |
| `content/member-providers-content.tsx` | 142 | `<ContextualEmptyState variant="no-data" context="provider-assignments" />` |

Remove any unused icon imports after migration.

---

### #7 — Create QuickActionsGrid for dashboard
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/home/quick-actions-grid.tsx`

Responsive row of 4 action buttons:

```typescript
interface QuickActionsGridProps {
  members: FamilyMemberResponse[];
}
```

Actions:
1. **Add Record** (`FileText` icon) → opens quick-add-record-dialog or navigates to `/people/{lastMember}/records/new`
2. **Add Reminder** (`BellPlus` icon) → navigates to `/reminders/new`
3. **Smart Entry** (`Sparkles` icon) → focuses SmartEntryBar (or navigates to `/ai-tools`)
4. **Chat AI** (`MessageSquare` icon) → navigates to `/chat`

Styling: `Button variant="outline" size="sm"` with icon + label. Layout: `grid grid-cols-2 md:grid-cols-4 gap-2`. Wire to existing routing/dialogs (same targets as `UniversalQuickAdd`).

---

### #8 — Create HealthOverviewCard for dashboard sidebar
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/home/health-overview-card.tsx`

Compact 2×2 stat grid inside `Card size="sm"`:

```typescript
interface HealthOverviewCardProps {
  summary: DashboardSummary;
  memberNames: Record<string, string>;
}
```

Four stat cells:
1. **Records this month** — `summary.record_activity.total_last_30_days` with by-type breakdown as tiny colored badges (blue=lab, green=consultation, violet=prescription, amber=vitals)
2. **Vaccinations** — total from `summary.vaccination_status.total_vaccinations`, overdue count from `summary.vaccination_status.overdue_count` highlighted red if > 0
3. **Risk summary** — high/moderate/low from `summary.risk_summary` as colored dots with counts (red/amber/green)
4. **Medications** — `summary.medication_summary.total_active_medications` total, refill reminders count

Uses existing Card, Badge components. Each cell: icon + value + subtitle label.

---

### #9 — Simplify home.tsx to pass full DashboardSummary
- **Status:** pending
- **Blocked by:** none
- **Modify:** `frontend/src/pages/home.tsx`

Current (lines 48-84) manually destructures `summary`:
- Maps `summary.members` to `FamilyMemberResponse[]` with field-by-field mapping
- Constructs a narrow `DashboardStats` object from `summary.providers_count`, `summary.conversations_count`, etc.
- Passes separate `members`, `householdName`, `stats`, `records` props

Change to:
- Pass the raw `summary: DashboardSummary` to `HomeContent`
- `HomeContent` already calls `useDashboardSummary()` internally so has access to all data
- Keep redirect logic (auth error → login, no members → onboarding) and error handling unchanged

---

### #10 — Restructure home-content.tsx to two-column layout
- **Status:** pending
- **Blocked by:** #7, #8, #9
- **Modify:** `frontend/src/components/content/home-content.tsx`

**Props change:** `HomeContentProps` accepts `summary: DashboardSummary` instead of separate `members/stats/records`

**Layout restructure** from `max-w-3xl mx-auto space-y-4` to:

```
max-w-5xl mx-auto
├── Zone A (full width)
│   ├── Greeting + date + member count (keep existing gradient text style)
│   ├── QuickActionsGrid (from #7)
│   └── SmartEntryBar (existing)
├── Zone B (lg:grid-cols-[1fr_320px] gap-6)
│   ├── Left column (primary)
│   │   ├── AlertStrip (existing, conditional on alerts.length > 0)
│   │   ├── Section heading: "Recent Activity"
│   │   ├── ActivityFeed (existing)
│   │   └── ContextualSection (existing)
│   └── Right column (secondary — "Insights" sidebar)
│       ├── FamilyStrip (from #11, with scores)
│       ├── HealthOverviewCard (from #8)
│       └── Member score cards (if summary.scores exists)
```

Update `HomeSkeleton` to match new proportions (delegated to #20).

---

### #11 — Add health scores to FamilyStrip component
- **Status:** pending
- **Blocked by:** #10
- **Modify:** `frontend/src/components/home/family-strip.tsx`

Add optional `scores?: MemberScore[]` prop.

Desktop (inside sidebar column):
- Render as vertical stack instead of horizontal scroll
- Each member row: avatar + name + mini `HealthScoreRing` (size=48)
- Tooltip on score ring: "Score: 72/100 — Good"

Mobile:
- Keep existing horizontal scroll behavior unchanged

Score labels:
- >= 70: "Good" (green)
- 40-69: "Needs attention" (amber)
- < 40: "At risk" (red)

Prop is optional — component works without scores (backward compatible).

---

### #12 — Improve ActivityFeed empty state
- **Status:** pending
- **Blocked by:** #10
- **Modify:** `frontend/src/components/home/activity-feed.tsx`

Replace inline empty text (plain "No recent activity" `text-sm text-muted-foreground`) with shared `EmptyState` component:
- Icon: `Activity` or `Clock` from lucide-react
- Title: "No recent activity"
- Description: "Health records and reminders will appear here as you add them."
- Action: Link to "Add your first record"

---

### #13 — Create wizard Step 1: Type Selection
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/records/wizard/step-type-selection.tsx`

Presentational step component. Source: record-form.tsx lines ~421-701.

```typescript
interface StepTypeSelectionProps {
  recordType: RecordType | undefined;
  onRecordTypeChange: (type: RecordType) => void;
  recordDate: string;
  onRecordDateChange: (date: string) => void;
  recordTime: string;
  onRecordTimeChange: (time: string) => void;
  uploadSection?: React.ReactNode;
  errors: Record<string, { message?: string }>;
}
```

Renders:
- Record type `<Select>` with all `RECORD_TYPE_OPTIONS`
- Record date `<Input type="date">` (required)
- Record time `<Input type="time">` (optional)
- File upload/extraction area (received as `uploadSection` React node from wizard parent)

Purely presentational — all state and callbacks come from parent.

---

### #14 — Create wizard Step 2: Visit Details
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/records/wizard/step-visit-details.tsx`

Presentational step component. Source: record-form.tsx lines ~703-916, 919-956.

```typescript
interface StepVisitDetailsProps {
  providers: ProviderResponse[];
  selectedProviderId: string;
  onProviderChange: (id: string) => void;
  onAddProvider: () => void;
  chiefComplaint?: string;
  onChiefComplaintChange: (value: string) => void;
  diagnosis: string;
  onDiagnosisChange: (value: string) => void;
  nextReviewDate?: string;
  onNextReviewDateChange: (value: string) => void;
  tags: string[];
  onTagsChange: (tags: string[]) => void;
  tagInput: string;
  onTagInputChange: (value: string) => void;
  isDoctorVisit: boolean;
  errors: Record<string, { message?: string }>;
}
```

Renders:
- Provider `<Select>` with "Add Provider" trigger button (calls `onAddProvider`, dialog lives in parent)
- Chief complaint `<Input>` (only if `isDoctorVisit`)
- Diagnosis `<Textarea>`
- Next review date `<Input type="date">`
- Tags input with badge display + remove buttons

Purely presentational.

---

### #15 — Create wizard Step 3: Clinical Data
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/records/wizard/step-clinical-data.tsx`

Presentational step component. Source: record-form.tsx lines ~828-898, 958-982.

```typescript
interface StepClinicalDataProps {
  config: RecordTypeConfig | null;
  customValues: Record<string, string>;
  onCustomFieldChange: (key: string, value: string) => void;
  tableData: Record<string, Record<string, string>[]>;
  onTableChange: (key: string, rows: Record<string, string>[]) => void;
  onAutoFillBatch?: (tableKey: string, batchId: string) => void;
  autoFillBatches: ExtractionBatch[];
  notes: string;
  onNotesChange: (value: string) => void;
  clinicalData: string;
  onClinicalDataChange: (value: string) => void;
  isDoctorVisit: boolean;
}
```

Renders:
- `<TypeSpecificFields>` (existing component, reused directly)
- `<DynamicTable>` for prescriptions, lab tests (existing component, reused directly)
- Auto-fill batch picker for extracted data (if batches available)
- Notes `<Textarea>`
- Clinical data fallback `<Textarea>` (only for types without structured content)

Purely presentational. Reuses existing `TypeSpecificFields` and `DynamicTable`.

---

### #16 — Create wizard Step 4: Review & Save
- **Status:** pending
- **Blocked by:** none
- **New file:** `frontend/src/components/records/wizard/step-review.tsx`

New presentational step (no direct source — this is the new review step).

```typescript
interface StepReviewProps {
  recordType: RecordType | undefined;
  recordDate: string;
  recordTime?: string;
  providerName: string | null;
  chiefComplaint?: string;
  diagnosis: string | null;
  customValues: Record<string, string>;
  tableData: Record<string, Record<string, string>[]>;
  notes: string;
  clinicalData: string;
  tags: string[];
  uploadedFiles: { name: string }[];
  config: RecordTypeConfig | null;
  isPending: boolean;
  isEditing: boolean;
  onSubmit: () => void;
  onReset: () => void;
}
```

Renders:
- Summary `Card` with all entered data in a clean read-only layout:
  - Type badge + date
  - Provider name
  - Diagnosis
  - Table data (prescriptions, labs) as read-only table
  - Tags as badges
  - Notes
- File attachment status (file names)
- Medication preview if prescriptions detected in clinical data
- Submit button (`isPending` shows loading spinner)
- Reset button (ghost)

---

### #17 — Create RecordFormWizard orchestrator
- **Status:** pending
- **Blocked by:** #2, #13, #14, #15, #16
- **New file:** `frontend/src/components/records/wizard/record-form-wizard.tsx`

Same `RecordFormProps` interface as current `RecordForm` — drop-in replacement:
```typescript
interface RecordFormProps {
  action: (prevState: unknown, formData: FormData) => Promise<unknown>;
  providers: ProviderResponse[];
  onProviderCreated?: (provider: ProviderResponse) => void;
  onSaveComplete?: () => void;
  record?: HealthRecordResponse;
  memberId?: string;
  defaultType?: RecordType;
  defaultProviderId?: string;
  defaultChiefComplaint?: string;
}
```

Manages:
- `currentStep` state (0-3)
- `useActionState` for form submission
- `useForm` (react-hook-form + zod resolver) for validation
- `useFileExtraction` hook for document upload/OCR
- All 20+ `useState` calls (customValues, tableData, notes, tags, provider list, medication sync, etc.)

Renders:
- `<Stepper>` at top (from #2)
- Conditional step component based on `currentStep`
- `<form>` wrapper
- Medication confirmation dialog (triggered after save if doctor visit with prescriptions)
- Medication sync dialog (triggered after medication confirmation)

Navigation:
- Non-linear: click stepper to jump between steps
- Auto-skip step 0 if `defaultType` is provided
- Save button only on step 3 (Review)
- Back/Next footer buttons

---

### #18 — Wire RecordFormWizard into record-new.tsx
- **Status:** pending
- **Blocked by:** #17
- **Modify:** `frontend/src/pages/record-new.tsx`

Changes:
1. Import `RecordFormWizard` from `@/components/records/wizard/record-form-wizard` instead of `RecordForm`
2. Pass same props — it's a drop-in replacement with identical `RecordFormProps`
3. Add "Switch to classic form" link below the card
4. Toggle stores preference in `localStorage` key `"record-form-mode"` (`"wizard"` | `"classic"`)
5. On mount, read preference and render the chosen component

**Do NOT modify `record-edit.tsx`** — it continues using `RecordForm` directly.

---

### #19 — Polish onboarding wizard with stepper, progress, skip
- **Status:** pending
- **Blocked by:** #2
- **Modify:** `frontend/src/components/content/onboarding-wizard.tsx`

Changes:
1. **Replace step indicator** (lines 118-139) with shared `<Stepper>` from #2
2. **Add progress bar** below stepper: `<Progress value={(step / (STEPS.length - 1)) * 100} className="h-1" />`
3. **Step 2 "optional" badge**: Add `<Badge variant="outline" className="ml-2 text-[10px]">optional</Badge>` next to "Provider" CardTitle
4. **Explicit skip button**: Add separate `Button variant="ghost" size="sm"` labeled "Skip for now" below the provider form fields on step 2, with `<Tooltip>` text "You can add providers later from the Providers page"
5. **Step transitions**: Add `animate-fade-in-up` class + `key={step}` on step content wrapper for smooth transitions between steps
6. **Step descriptions**: Verify CardDescription text is consistent for all 4 steps (already partially present)
7. Remove old custom step indicator code (lines 118-139)

---

### #20 — Update HomeSkeleton for new dashboard layout
- **Status:** pending
- **Blocked by:** #10
- **Modify:** `frontend/src/components/content/home-content.tsx` (HomeSkeleton function, lines 200-215)

Current skeleton assumes `max-w-3xl` single column. Update to reflect `max-w-5xl` two-column layout:

```
max-w-5xl mx-auto
├── Skeleton: greeting row (h-5 w-36 + h-4 w-52)
├── Skeleton: quick actions row (4 × h-9 w-24)
├── Skeleton: smart entry bar (h-12 w-full)
├── Skeleton: two-column grid (lg:grid-cols-[1fr_320px])
│   ├── Left: activity feed skeleton (h-48 rounded-lg)
│   └── Right: family strip (h-24) + health overview (h-36)
```

Use `animate-pulse` skeleton blocks matching the proportions of the real content.

---

## Verification Checklist

After all tasks complete:

### Area 1 — Dashboard
- [ ] Dashboard loads with two-column layout on desktop (>= 1024px)
- [ ] Dashboard collapses to single column on mobile (< 1024px)
- [ ] Quick action buttons navigate to correct pages/dialogs
- [ ] Health overview card shows real aggregate data
- [ ] Family strip shows health scores on desktop with tooltips
- [ ] Family strip remains horizontal scroll on mobile
- [ ] Activity feed empty state shows guidance + action
- [ ] HomeSkeleton matches loaded layout proportions
- [ ] Dark mode renders correctly

### Area 2 — Record Wizard
- [ ] New record page shows wizard with stepper
- [ ] Step 1: type selection + file upload works
- [ ] Step 2: provider + visit details works
- [ ] Step 3: clinical data fields + dynamic tables work
- [ ] Step 4: review shows read-only summary, save button works
- [ ] Medication sync dialog still appears for doctor visits with prescriptions
- [ ] "Switch to classic form" toggle works
- [ ] Record edit page still uses classic form (unchanged)
- [ ] Quick forms (blood glucose, vitals, parkinsons) still work from quick-add dialog
- [ ] Smart entry still works independently
- [ ] Document extraction + auto-fill still works
- [ ] `defaultType` auto-skips step 1

### Area 3 — Empty States & Onboarding
- [ ] Each empty page shows contextual illustration + guidance + action button
- [ ] Filtered empty pages show "no matching" variant
- [ ] Onboarding wizard shows shared stepper component
- [ ] Progress bar updates with each step
- [ ] Step 2 shows "optional" badge
- [ ] "Skip for now" button has tooltip
- [ ] Step transitions animate smoothly

### Build & Type Check
```bash
cd frontend && npx tsc --noEmit    # Type check
cd frontend && npm run build       # Production build
cd backend && uv run pytest        # Backend unchanged
```
