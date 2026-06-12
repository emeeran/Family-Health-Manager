# AI Tools — Task List

> Verified against actual codebase on 2026-06-12.
> All 14 original AI tool improvements complete + provider configuration feature added.

---

## ✅ MA-2: Provider Health Dashboard + Provider Configuration

**Impact:** ★★★★★ | **Status:** ✅ Done

### What was done

**Backend:**
- `GET /ai/status` — tests each provider with configured model, returns availability + response time
- `GET/PUT /household/ai-provider-config` — CRUD for per-household provider config
- `schemas/ai_provider_config.py` — `ProviderConfigItem`, `AIProviderConfig`, `AVAILABLE_MODELS`, `PROVIDER_LABELS`
- All 5 provider functions accept optional `model` parameter
- `AIService` accepts `household_id`, lazy-loads config from household `settings_json`
- Dynamic failover chain built from config instead of hardcoded array
- All 23 router call sites updated to pass `household_id`

**Frontend:**
- AI Providers tab with two sections:
  - **Provider Configuration** — reorder (up/down), enable/disable toggle, model selector (dropdown or free text for Ollama), auto-saves on every change
  - **Live Status** — check provider connectivity with refresh button

### Files changed
- **NEW:** `backend/app/schemas/ai_provider_config.py`
- **Modified:** `backend/app/schemas/household.py`, `backend/app/routers/household.py`, `backend/app/routers/ai.py`
- **Modified:** `backend/app/services/ai/__init__.py`, all 5 `providers/*.py`
- **Modified:** 10 router files for `household_id` passthrough
- **Modified:** `frontend/src/lib/types/household.ts`, `frontend/src/lib/api/household.ts`, `frontend/src/lib/api/ai.ts`
- **Modified:** `frontend/src/pages/settings.tsx`

---

## ✅ MA-1: Document Upload UI for AI Extraction

**Impact:** ★★★★★ | **Status:** ✅ Done

### What was done
- Created `frontend/src/pages/ai-tools/document-extraction.tsx` wrapping `BatchUploadQueue` in `AiToolsSubPage` layout
- Added tool card to `ai-tools-hub.tsx` with `FileUp` icon and indigo color
- Added lazy import + route in `router.tsx`

### Files changed
- **New:** `frontend/src/pages/ai-tools/document-extraction.tsx`
- **Modified:** `frontend/src/pages/ai-tools/ai-tools-hub.tsx`, `frontend/src/router.tsx`

---

## Original 14 AI Tool Improvements — All Complete

| # | Item | Status |
|---|------|--------|
| 1 | QW-1: Cancel button for AI generations | ✅ |
| 2 | QW-2: Meaningful progress indicators | ✅ |
| 3 | QW-3: Smart entry examples & guidance | ✅ |
| 4 | QW-4: Error recovery with retry | ✅ |
| 5 | QW-5: Verification polling after generation | ✅ |
| 6 | QW-6: Conversation title editing | ✅ |
| 7 | ME-1: Real PDF generation | ✅ |
| 8 | ME-2: Conversation search | ✅ |
| 9 | ME-3: Backend provider retry with backoff | ✅ |
| 10 | ME-4: Drug interaction cache transparency | ✅ |
| 11 | ME-5: Unified AI error state component | ✅ |
| 12 | MA-1: Document upload UI for AI extraction | ✅ |
| 13 | MA-2: Provider health dashboard + config | ✅ |
| 14 | MA-3: OpenAI provider integration | ✅ |
