If you've ever tried to recall when your father last had his HbA1c checked, you know the answer is buried somewhere in a drawer of lab reports, a gallery of phone photos, or a folder of PDFs nobody opens. I wanted a system where asking "What was Dad's last blood work?" actually returns the right answer—instantly, accurately, and without me second-guessing whether the AI made it up. Here's how I built it.

## The Goal

A family health record manager that:

- Extracts structured data from medical documents (PDFs, photos) using AI vision
- Answers health questions about your family with conversation AI
- Catches when the AI gets it wrong—using a second AI to fact-check the first
- Tracks medications, lab trends, vaccinations, and reminders
- Runs entirely self-hosted—your health data never leaves your machine

## The Solution

A FastAPI + React application with multi-provider AI failover, real-time cross-verification, and unambiguous medical data formatting. Named after the project: **DAWNSTAR Family Health Keeper**.

## How It Works

**Document Ingestion:** Upload a PDF or photo. A vision-capable AI dismantles it into structured atoms—lab tests with reference ranges, prescriptions with dosage timing, diagnoses with dates. The PDF ceases to be a PDF. It becomes a row you can trend, a value you can compare, a date you can trust because it was extracted, not typed.

**Context Assembly:** Before the conversational AI speaks, it receives a curated evidentiary brief: every family member's timeline, every lab trend normalized (Glycosylated Hb, HB A1C, and HbA1c all resolve to one canonical name), and dates rendered in an unambiguous format (09-Apr-2026, never 2026-04-09 which models confuse). The AI has no excuse to fabricate what is already in front of it.

**Response Verification:** Every AI response is independently audited by a different model from a different provider. If GPT-4o-mini generated the answer, Gemini verifies it. Discrepancies are structured, severity-ranked, and surfaced as warnings: wrong date, wrong value, wrong family member attribution, omitted fact, fabrication. The verdict appears as a badge under each response—green for verified, amber for warnings, muted for unverifiable.

```
User: "When was Dad's last HbA1c?"

AI:     "Dad's last HbA1c was 8.9%, recorded on 09-Apr-2026."
Audit:  ✅ Verified — 3 claims checked, 0 warnings
```

## The Setup

```bash
# Clone and start
git clone https://github.com/emeeran/sdd-health-manager.git
cd sdd-health-manager

# One command starts everything
./dev.sh
# → Backend on :8003, Frontend on :3003
```

The `dev.sh` script spins up both the FastAPI backend and Vite frontend dev servers. SQLite in development, PostgreSQL in production. No Docker required for local use.

## The Architecture

```
Document Upload (PDF/Image)
        │
        ▼
┌─────────────────────┐
│  Extraction Pipeline │
│  PyMuPDF → OCR →     │
│  Vision AI (multi-   │
│  provider failover)  │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Structured Record   │
│  lab tests, Rx,      │
│  conditions, dates   │
│  (queryable JSON)    │
└────────┬────────────┘
         │
         ▼
    User asks a question
         │
         ▼
┌──────────────────────────────────┐
│         AIService.chat()         │
│                                  │
│  1. Assemble context:            │
│     • Member demographics        │
│     • Last 20 records/member     │
│     • Full lab trend history     │
│     • DD-Mon-YYYY dates          │
│                                  │
│  2. Call primary AI provider     │
│     (Gemini → OpenRouter →       │
│      Groq → GPT-4o-mini)        │
│                                  │
│  3. Verify with DIFFERENT model  │
│     (skip the one that answered) │
│                                  │
│  4. Return response + verdict    │
└──────────────────────────────────┘
         │
         ▼
   Frontend renders:
   ┌──────────────────────────────┐
   │ 🤖 Dad's last HbA1c was     │
   │    8.9% on 09-Apr-2026.     │
   │                              │
   │  ✅ Verified (tap for detail)│
   └──────────────────────────────┘
```

## Key Technical Decisions

### 1. Unambiguous Date Formatting

AI models confuse `2026-04-09` with `09-04-2026` or `04-09-2026`. Every date in the system is rendered as `DD-Mon-YYYY` (e.g., `09-Apr-2026`) before reaching the model:

```python
@staticmethod
def _fmt_date(d: object) -> str:
    parsed = datetime.strptime(str(d)[:10], "%Y-%m-%d")
    return parsed.strftime("%d-%b-%Y")  # "09-Apr-2026"
```

### 2. Canonical Lab Test Names

The same test appears in records as "Glycosylated HbA1c", "HB A1C", "HbA1C", and "HbA1c". A normalization layer collapses all variants:

```python
KEY_TESTS = {
    "hba1c": "HbA1c",
    "hb a1c": "HbA1c",
    "glycosylated": "HbA1c",
    "fasting glucose": "Fasting Glucose",
    "total cholesterol": "Total Cholesterol",
}
```

### 3. Cross-Provider Verification

The verification guard calls a **different** AI provider than the one that generated the response, eliminating single-model groupthink:

```python
async def _call_ai_excluding(self, prompt: str, exclude_provider: str):
    for provider_fn, label in providers:
        if label == exclude_provider:
            continue  # Skip the provider that generated the answer
        result = await provider_fn(prompt)
        ...
```

### 4. Structured Clinical Data Extraction

Raw clinical JSON (often 5KB+) isn't just truncated—it's parsed and summarized:

```python
# Before: 300-char truncation cutting off lab results
# After:  Extract each lab test, prescription, condition separately
for test in data.get("lab_results", []):
    line = f"{test['test_name']}: {test['result']} (ref: {test['ref_value']})"
```

### 5. Smart Form Updates

Edit forms only send fields that actually changed, using `exclude_unset` semantics. Previously, sending `null` for fields not in the form would **clear existing data**:

```typescript
// Before: Cleared prescription_text on every doctor visit edit
prescription_text: (formData.get("prescription_text") as string) || null

// After: Only send if the field exists in the form
const prescriptionText = formData.get("prescription_text") as string;
if (prescriptionText !== null) data.prescription_text = prescriptionText || null;
```

## Usage Examples

```
You: "Summarize my family's recent health activity"
AI:  "Meeran had a doctor visit on 12-Apr-2026 with Dr. Ramachandiran.
      Key findings: HbA1c at 8.9% (elevated), Lipase elevated at 120 IU/L.
      Jenitha's hemoglobin was 8.5 g/dL on 15-Mar-2026 (low)."
Audit: ✅ Verified

You: "What medications is my family currently taking?"
AI:  [Lists all current prescriptions from structured clinical_data]
Audit: ⚠️ Warnings: 1 omission (Glimepiride not mentioned)
       Correction: Glimepiride 2mg prescribed on 12-Apr-2026

You: "Any overdue health reminders?"
AI:  [Checks reminder schedule against today's date]
```

## The Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | React 19, Vite, shadcn/ui | Fast dev, accessible components |
| Backend | Python 3.11+, FastAPI | Async, typed, automatic OpenAPI |
| Database | SQLite → PostgreSQL | Zero-config dev, production-ready |
| AI Providers | Gemini → OpenRouter → Groq → OpenAI | Free tier failover chain |
| Verification | Second provider from same chain | Cross-model fact checking |
| Packaging | `uv` (not pip) | 10x faster dependency resolution |

## Requirements

```bash
# Backend
Python 3.11+, uv

# AI Keys (at least one)
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
GROQ_API_KEY=...

# Frontend
Node.js 18+

# Document processing
poppler-utils  # PDF text extraction
```

## Why This Matters

Most families manage health records the same way: a drawer of papers, a phone gallery of photos, and a fading memory of which doctor said what. When a medical emergency hits, you're digging through folders instead of making decisions.

The AI chatbot layer helps—but only if you can trust it. Medical misinformation from a confident AI isn't just unhelpful; it's dangerous. The cross-verification guard doesn't promise perfection. It promises **transparency about imperfection**. When the system catches a swapped date or an omitted prescription, it tells you—every single time.

The modular architecture makes it straightforward to extend: add new record types in `record-type-configs.ts`, swap AI providers in the failover chain, or add new verification checks in the prompt template. Everything runs self-hosted because your family's health data should live on your machine, not someone else's cloud.

Happy tracking!
