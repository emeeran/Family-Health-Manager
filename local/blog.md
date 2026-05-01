## Whose Health Is It, Anyway?

### Part I: Challenges — The Broken Chain of Custody

A family is a small hospital that doesn't know it is one.

Between a father's quarterly HbA1c checks, a mother's thyroid panels, a child's vaccination schedule, and an aging grandparent's polypharmacy, a typical household manages dozens of clinical touchpoints per year. Yet the system designed to track them was built for institutions, not families. Each clinic keeps its own silo. Each lab prints its own report. Each pharmacy dispenses with its own app. The result: **health data exists in abundance, but ownership is fractured**.

The family has no medical records department. There is no triage nurse at home to notice that a hemoglobin reading of 8.5 g/dL has been slowly declining across three consecutive visits. No pharmacist cross-referencing that the new prescription interacts with the one from a different doctor three months ago. The data is there — in a drawer, in a photo gallery, in a forgotten email attachment — but it speaks no language the family can hear.

Enter the AI chatbot: a promise to bridge the literacy gap. But this bridge is built on sand. Language models are **convincing improvisers**, not faithful reporters. Ask one when the last glucose test was, and it will produce a date — sometimes correct, sometimes swapped, always confident. It will mix up family members, confuse tests that share abbreviations, and omit records it was never shown because the context window ran out mid-way through a ten-year medical history. The pain is no longer just "we can't find the data." It is now "the AI found it, and it's wrong, and we can't tell."

Three fractures: **fragmented custody, silent signals, and the authority illusion**.

### Part II: Resolution — Listening to the Data Before It Speaks

The resolution does not begin with a chatbot. It begins with **reading**.

Every document that enters the system — a crumpled lab report, a photographed prescription slip, a multi-page discharge summary — is passed through a vision-capable extraction pipeline. Not to store it as an image, but to **dismantle it into structured, queryable atoms**: test name, numeric result, reference range, clinical note, prescribing provider, follow-up date. The PDF ceases to be a PDF. It becomes a row you can trend, a value you can compare, a date you can trust because it was extracted, not typed.

Then comes the conversation layer — but grounded, not free-floating. Before the model generates a single word, it receives a **curated evidentiary brief**: every family member's timeline, every lab trend normalized so that "Glycosylated Hb" and "HB A1C" and "HbA1c" resolve to the same signal. Dates are rendered in formats that admit no ambiguity. Context is capped not by what fits, but by what matters — the last twenty records per member, plus a full historical sweep of every key biomarker the system has ever seen.

And then — the crucial layer — the architecture refuses to trust itself. Every response is **audited in real time** by a different model from a different provider, given the same evidence, asked a single question: *Is this claim supported by the data?* Discrepancies are not hidden. They are structured, severity-ranked, and surfaced to the user as warnings: wrong date, wrong value, wrong attribution, omitted fact, outright fabrication. The system's confidence is never assumed. It is **earned, per claim, per response**.

### Part III: Implementation — The Instrumentation of Doubt

**Technical Stack:**

| Concern | Technology |
|---|---|
| Presentation | React 19, Vite, shadcn/ui component library, SWR for data freshness |
| API Layer | FastAPI (Python 3.11+), Pydantic v2 validation, async throughout |
| Persistence | SQLAlchemy async ORM — SQLite in development, PostgreSQL in production |
| Document Ingestion | PyMuPDF text extraction → OCR fallback → multi-provider vision AI extraction |
| Primary AI | Failover chain: Gemini 2.5 Flash → OpenRouter → Groq Llama-4-Scout → OpenAI GPT-4o-mini |
| Verification Guard | Second provider from the same chain, excluding whichever generated the original response |
| Inter‑Process Communication | Structured JSON contracts between all layers — no free‑form handoffs |

**Operational Workflow:**

```
                         ┌──────────────────┐
                         │  Document Upload  │
                         │  (PDF / Image)    │
                         └────────┬─────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │     Extraction Pipeline      │
                    │  Text → OCR → Vision AI      │
                    │  (multi-page, multi-provider) │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │   Structured Health Record   │
                    │  lab tests, Rx, conditions,  │
                    │  dates, providers, trends    │
                    └─────────────┬──────────────┘
                                  │
              ┌───────────────────▼───────────────────┐
              │           User Opens Chat              │
              └───────────────────┬───────────────────┘
                                  │
         ┌────────────────────────▼────────────────────────┐
         │              AIService.chat()                    │
         │                                                  │
         │  1. Assemble context:                            │
         │     • Member demographics + conditions           │
         │     • Recent records (20/member)                 │
         │     • Full lab trends (ALL records, key tests)   │
         │     • Unambiguous DD-Mon-YYYY dates              │
         │                                                  │
         │  2. Call primary AI provider (failover chain)     │
         │     → response_text, provider_label               │
         │                                                  │
         │  3. Persist messages to database                  │
         │                                                  │
         │  4. Fire VerificationService.verify():            │
         │     • Skip the provider that generated answer     │
         │     • Second model checks every claim             │
         │     • Returns: verified | warnings | unverifiable │
         │     • Structured warnings with severity + fix     │
         └────────────────────────┬────────────────────────┘
                                  │
              ┌───────────────────▼───────────────────┐
              │           API Response                  │
              │  • assistant_message                    │
              │  • verification (if resolved in < 3s)   │
              │  • OR: frontend polls at 1s intervals   │
              └───────────────────┬───────────────────┘
                                  │
              ┌───────────────────▼───────────────────┐
              │           Frontend Render               │
              │                                         │
              │  ┌───────────────────────────────────┐  │
              │  │ Your last HbA1c was 8.9%, taken   │  │
              │  │ on 09-Apr-2026 by Dr. Sharma.     │  │
              │  │                                   │  │
              │  │  ✅ Verified  (click for details) │  │
              │  └───────────────────────────────────┘  │
              │                                         │
              │  ┌───────────────────────────────────┐  │
              │  │ Metformin was prescribed in June. │  │
              │  │                                   │  │
              │  │  ⚠ Warnings                       │  │
              │  │  • wrong_date: July, not June     │  │
              │  │  • omission: Glimepiride omitted  │  │
              │  └───────────────────────────────────┘  │
              └─────────────────────────────────────────┘
```

**Final Deliverables:**

- **Intelligent document extraction** — Vision AI parses medical documents into structured records: lab tests with reference ranges, prescriptions with timing, diagnoses with dates. Multi-page PDFs are handled page-by-page with merging. No manual data entry.

- **Context-grounded conversational AI** — A chatbot that receives not a prompt but a brief: curated family health summaries, canonical lab test names, unambiguous date formats, and full biomarker trend histories. System prompts enforce disambiguation rules (Hb vs. HbA1c, member separation).

- **Real-time cross-provider verification guard** — Every AI response is independently audited by a second model. Results are persisted as `ResponseVerification` records with structured JSON warnings. The guard never blocks the user — it layers in via timeout-gated inline delivery or silent polling fallback.

- **Verification-aware UI** — Each assistant message carries a badge: green for verified, amber for warnings with expandable corrections, muted for unverifiable. Users see not just the answer but the system's confidence in the answer.

- **Resilient multi-provider failover** — Four AI providers in chain with automatic fallback. Verification intentionally uses a different provider than the one that generated the response, eliminating single-model groupthink.

The system does not promise perfection. It promises **transparency about imperfection** — and in a domain where a wrong date or a swapped test name can change a clinical decision, that transparency is the difference between a tool and a liability.
