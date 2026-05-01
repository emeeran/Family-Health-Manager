# Code Fix Plan

> Phase p5.5 — Bloat and redundancy fixes derived from code review.

---

## Priority 1: Remove Duplicate Code (Highest Impact)

### Task 1.1: Extract `get_household_from_token` to `core/deps.py`

**Files affected:** 10 routers + `core/deps.py`
**Lines saved:** ~180

**Steps:**
1. Add `get_household_from_token` dependency to `core/deps.py`
2. Remove duplicate function from:
   - `routers/members.py`
   - `routers/providers.py`
   - `routers/provider_assignments.py`
   - `routers/health_records.py`
   - `routers/attachments.py`
   - `routers/ai.py`
   - `routers/conversations.py`
   - `routers/reminders.py`
   - `routers/notifications.py`
   - `routers/audit.py`
3. Update imports in all routers to use `from app.core.deps import get_household_from_token`

---

### Task 1.2: Consolidate Update Patterns

**Files affected:** 4 service files
**Lines saved:** ~20

**Steps:**
1. Create helper function in `core/database.py`:
   ```python
   async def update_model(db: AsyncSession, model: Base, **kwargs) -> Base:
       """Update model fields from kwargs."""
       for key, value in kwargs.items():
           if value is not None and hasattr(model, key):
               setattr(model, key, value)
       await db.flush()
       return model
   ```
2. Replace update loops in:
   - `services/member_service.py` (line 78-86)
   - `services/provider_service.py` (line 60-68)
   - `services/health_record_service.py` (line 97-105)
   - `services/reminder_service.py` (line 75-83)

---

## Priority 2: Remove Unused/Redundant Code

### Task 2.1: Remove Unused Middleware from `main.py`

**Files affected:** `main.py`
**Lines saved:** ~40

**Steps:**
1. Remove `user_context_middleware` function (lines 72-80)
2. Remove `http_exception_handler` decorator and function (lines 83-93)
3. Remove `general_exception_handler` decorator and function (lines 96-106)
4. Remove unused import `HTTPException` if no longer needed

---

### Task 2.2: Remove Unused Config Properties

**Files affected:** `core/config.py`
**Lines saved:** ~8

**Steps:**
1. Remove `jwt_secret` property (lines 48-50)
2. Remove `db_path` property (lines 52-54)
3. Update `core/security.py` to use `settings.SECRET_KEY` directly

---

### Task 2.3: Remove Unused Imports and Variables

**Files affected:** Multiple
**Lines saved:** ~10

**Steps:**
1. `storage.py`: Remove `import os` (line 1)
2. `auth.py`: Remove `security = HTTPBearer(auto_error=False)` (line 12)
3. `auth.py`: Remove unused import `HTTPAuthorizationCredentials`
4. `health_records.py`: Move `import base64` to module level (line 6)

---

### Task 2.4: Remove Unused Dependency

**Files affected:** `core/deps.py`
**Lines saved:** ~12

**Steps:**
1. Remove `get_optional_user` function (lines 46-56)
2. Remove unused import `status` from fastapi

---

## Priority 3: Simplify Verbose Code

### Task 3.1: Consolidate AI Provider Stub Methods

**Files affected:** `services/ai_service.py`
**Lines saved:** ~25

**Steps:**
1. Replace 5 methods (`_call_gemini`, `_call_groq`, `_call_openrouter`, `_call_ollama_cloud`, `_call_ollama_local`) with single helper:
   ```python
   async def _call_provider(self, api_key: str | None, url: str | None = None) -> str | None:
       """Call AI provider if API key is configured."""
       if not api_key:
           return None
       # Placeholder - implement actual API call
       return None
   ```
2. Update `_call_ai` to use new helper
3. Remove placeholder comments

---

### Task 3.2: Simplify Medical History Parsing

**Files affected:** `services/member_service.py`
**Lines saved:** ~15

**Steps:**
1. Replace lines 35-46 with dict comprehension:
   ```python
   if medical_history:
       parts = {
           "Conditions": medical_history.conditions,
           "Allergies": medical_history.allergies,
           "Medications": medical_history.current_medications,
           "Surgeries": medical_history.past_surgeries,
       }
       member.medical_history_summary = "; ".join(
           f"{k}: {v}" for k, v in parts.items() if v
       ) or None
   ```

---

### Task 3.3: Simplify `get_brief_medical_history`

**Files affected:** `services/member_service.py`
**Lines saved:** ~10

**Steps:**
1. Replace lines 100-118 with cleaner parsing:
   ```python
   async def get_brief_medical_history(self, member_id: UUID) -> dict:
       """Get brief medical history summary for dashboard."""
       member = await self.get_member(member_id)  # Reuse existing method
       
       history = {"conditions": [], "allergies": [], "active_medications": []}
       if member.medical_history_summary:
           for part in member.medical_history_summary.split("; "):
               for key in ["Conditions", "Allergies"]:
                   if part.startswith(f"{key}:"):
                       history[key.lower()] = [
                           x.strip() for x in part.replace(f"{key}:", "").split(",")
                       ]
       
       history["active_medications"] = await self.get_active_medications(member_id)
       return history
   ```

---

### Task 3.4: Simplify Cursor Encoding

**Files affected:** `services/health_record_service.py`
**Lines saved:** ~5

**Steps:**
1. Replace lines 108-124 with:
   ```python
   import base64
   import json
   
   # ... in list_records:
   next_cursor = (
       base64.b64encode(
           json.dumps({"record_date": str(items[-1].record_date), "id": str(items[-1].id)}).encode()
       ).decode()
       if has_more and items
       else None
   )
   ```

---

### Task 3.5: Simplify `get_active_medications`

**Files affected:** `services/member_service.py`
**Lines saved:** ~8

**Steps:**
1. Replace lines 120-147 with list comprehension:
   ```python
   async def get_active_medications(self, member_id: UUID) -> list[dict]:
       """Get active medications from prescription records."""
       today = date.today()
       result = await self.db.execute(
           select(HealthRecord)
           .where(
               HealthRecord.family_member_id == member_id,
               HealthRecord.record_type == RecordType.PRESCRIPTION,
               HealthRecord.is_deleted == False,
           )
           .order_by(HealthRecord.record_date.desc())
           .limit(10)
       )
       return [
           {
               "name": r.clinical_data or "Unknown",
               "strength": "",
               "dose": r.prescription_text or "",
               "prescribed_by": r.provider_id,
           }
           for r in result.scalars().all()
           if r.next_review_date is None or r.next_review_date >= today
       ]
   ```

---

## Priority 4: Clean Up Response Builders

### Task 4.1: Fix Provider Assignment Response

**Files affected:** `routers/provider_assignments.py`
**Lines saved:** ~5

**Steps:**
1. Update `assign_provider` endpoint to return proper response model
2. Add provider/member name lookup or remove those fields from response

---

### Task 4.2: Simplify Conversation Creation

**Files affected:** `routers/conversations.py`
**Lines saved:** ~3

**Steps:**
1. Replace manual Conversation construction with helper if pattern repeats

---

## Priority 5: Remove Verbose Wrappers

### Task 5.1: Inline `PaginationParams.get_limit()`

**Files affected:** `core/deps.py` + call sites
**Lines saved:** ~4

**Steps:**
1. Remove `get_limit()` method from `PaginationParams`
2. Replace call sites with `min(params.limit, 100)`

---

## Summary

| Priority | Task | Files | Lines Saved |
|----------|------|-------|-------------|
| 1 | Extract `get_household_from_token` | 11 | ~180 |
| 1 | Consolidate update patterns | 5 | ~20 |
| 2 | Remove unused middleware | 1 | ~40 |
| 2 | Remove unused config properties | 2 | ~8 |
| 2 | Remove unused imports | 5 | ~10 |
| 2 | Remove unused dependency | 1 | ~12 |
| 3 | Consolidate AI provider stubs | 1 | ~25 |
| 3 | Simplify medical history parsing | 1 | ~15 |
| 3 | Simplify `get_brief_medical_history` | 1 | ~10 |
| 3 | Simplify cursor encoding | 1 | ~5 |
| 3 | Simplify `get_active_medications` | 1 | ~8 |
| 4 | Fix provider assignment response | 1 | ~5 |
| 5 | Inline `get_limit()` | 2 | ~4 |
| **Total** | | **32** | **~342** |

---

## Execution Order

1. **Task 1.1** — Extract `get_household_from_token` (highest impact, no risk)
2. **Task 2.1** — Remove unused middleware (clean startup)
3. **Task 2.2-2.4** — Remove unused config/imports (no risk)
4. **Task 3.1** — Consolidate AI stubs (cleaner code)
5. **Task 1.2** — Consolidate update patterns (DRY)
6. **Task 3.2-3.5** — Simplify verbose code (readability)
7. **Task 4.1-4.2** — Fix response builders (correctness)
8. **Task 5.1** — Inline wrapper (minor cleanup)

---

## Testing Strategy

After each priority group:
1. Run `make lint` (ruff + mypy)
2. Run `make test` (pytest)
3. Verify app starts: `uvicorn app.main:app --reload`

**Acceptance criteria:**
- All 76 unit tests pass
- No new mypy errors
- No new ruff errors
- App starts without errors
