# Requirements — Family Health Tracker

> Phase p1 — Functional and non-functional requirements derived from `docs/00-domain/DOMAIN.md`.
> All clarifications from Section 4 of DOMAIN.md have been resolved and baked in below.

---

## Resolved Clarifications

| # | Question | Resolution |
|---|----------|------------|
| 1 | Fields per record sub-type | See FR-010 through FR-016 for exact field lists. |
| 2 | File attachment limits | 25 MB max; MIME types: `application/pdf`, `image/jpeg`, `image/png`. |
| 3 | AI provider failover | Default: Google Gemini 2.5 Flash. Ordered fallback chain: Groq → OpenRouter → Ollama Cloud → Ollama Local. Use each provider's free tier; switch on rate-limit or quota exhaustion. AI selects the most competent model with the highest token limit available from the active provider. |
| 4 | Parkinson's tracking | Track symptom severity for tremor and stiffness (free-text severity scale). |
| 5 | Chatbot scope | Single Conversation aggregate with a `scope` discriminator: `member:<id>` for member-specific chat, `general` for general health Q&A. |
| 6 | Authentication | Username/password for v1 (single household). |
| 7 | Medical history on member add | Structured questionnaire wizard. |
| 8 | Email notifications | Deferred to post-v1. |
| 9 | Encryption at rest | SQLite SQLCipher (application-level, single-file DB). |
| 10 | Multi-household isolation | Separate databases per household (post-v1). |

---

## Functional Requirements

### Household Management

| ID | Priority | Statement | Acceptance Criterion |
|----|----------|-----------|----------------------|
| FR-001 | MUST | Create a household with a name and at least one family member. | A POST to the household endpoint returns 201 with a household ID and one linked member. |
| FR-002 | MUST | Add family members to a household with profile data (name, date of birth, relationship, gender). | A member record is persisted and retrievable via the household's member list. |
| FR-003 | MUST | Present a structured questionnaire when adding a new member to capture existing medical history (conditions, allergies, ongoing medications, past surgeries). | The questionnaire wizard collects at minimum: conditions (free text), allergies (free text), current medications (name, dose, duration), and saves them as initial health records. |
| FR-004 | MUST | Maintain a provider directory per household: doctor/clinic name, speciality, phone, address, and UHID per member. | A provider can be created, listed, and linked to one or more members with distinct UHIDs. |
| FR-005 | MUST | Display a Brief Medical History summary on each member's dashboard: key conditions, allergies, and active medications. | The dashboard returns a computed summary object from current data without additional user input. |
| FR-006 | MUST | Display an Active Medications table per member: Medicine & Strength, Dose, Duration, Prescribed By. | The table is populated from prescription records where end-date is in the future or null. |

### Health Records

| ID | Priority | Statement | Acceptance Criterion |
|----|----------|-----------|----------------------|
| FR-007 | MUST | Create a health record of a given type belonging to a family member with a recorded date. | The record is persisted, type-stamped, and appears on the member's timeline in chronological order. |
| FR-008 | MUST | Support the following health record types: Doctor Visit, Lab Test, Prescription, Imaging Report, Vaccination, Vital Signs, Allergy Entry, Condition Entry, Blood Glucose, HbA1c, Eyeglass Prescription, Parkinson's Symptom. | Each type is selectable at record-creation time and stored with its type-specific fields. |
| FR-009 | MUST | Soft-delete health records (append-only audit trail preserved). | A deleted record is marked inactive and excluded from default queries but retained in the audit log. |
| FR-010 | MUST | Store a Doctor Visit record with fields: Date, Chief Complaint, Consultant (link to Provider), Investigations, Diagnosis, Prescription (free text), Note, Next Review Date. | All fields are persisted and retrievable. Date and Chief Complaint are required. |
| FR-011 | MUST | Store a Lab Test record with fields: Date, Test Name, Result, Note/Insight. | All fields are persisted. Date and Test Name are required. |
| FR-012 | MUST | Store an HbA1c Tracking record with fields: Date, Result, eBG (estimated average blood glucose), Note. | All fields are persisted. Date and Result are required. |
| FR-013 | MUST | Store a Blood Glucose record with fields: Date, Time, Before/After Food (enum: `before_food`, `after_food`), Value (mg/dL). | All fields are persisted. Date, Time, and Value are required. |
| FR-014 | MUST | Store an Eyeglass Prescription record with fields: Date, Doctor (link to Provider), RE SPH/CYL/AXIS, LE SPH/CYL/AXIS, ADD, PD (RE, LE). | All fields are persisted. Date is required; refractive values default to 0.00. |
| FR-015 | MUST | Store a Parkinson's Symptom record with fields: Date, Tremor Severity (free text), Stiffness Severity (free text), Note. | All fields are persisted. Date is required. |
| FR-016 | MUST | Store a Prescription record with fields: Date, Medicine Name, Strength, Dose, Duration, Prescribed By (link to Provider), Note. | All fields are persisted. Date, Medicine Name, and Dose are required. |
| FR-017 | MUST | Attach one or more files (PDF, JPEG, PNG) to any health record. | Files are stored, MIME-validated, and retrievable. Rejected if MIME type is not in the allowed list or size exceeds 25 MB. |
| FR-018 | MUST | Display a chronological timeline of all health records per family member, ordered by date descending. | The timeline endpoint returns records in correct chronological order across all types. |
| FR-019 | MUST | Filter and search health records by keyword, tag, type, or date range. | A search query returns only records matching all specified criteria. |
| FR-020 | SHOULD | Export a member's timeline as a downloadable PDF. | A GET request returns a PDF file containing all timeline entries formatted chronologically. |
| FR-021 | MUST | Display a Lab Records list view per member: Date, Test Name, Result, Lab/Provider, Doctor Referred. | The view aggregates lab-related records into a tabular format. |

### AI Health Intelligence

| ID | Priority | Statement | Acceptance Criterion |
|----|----------|-----------|----------------------|
| FR-022 | MUST | Generate an AI Insight for a health record, contextualised by the member's past medical history. | Selecting a record and triggering "Generate Insight" returns a plain-language analysis referencing prior records. |
| FR-023 | MUST | Provide plain-language explanation of one or more selected health records ("explain these results"). | The AI returns an explanation in non-technical language. |
| FR-024 | MUST | Support multi-turn conversational Q&A with the AI, scoped to a specific member's health data or general health topics. | A conversation persists all messages; the user can switch scope via a `scope` field (`member:<id>` or `general`). |
| FR-025 | MUST | Persist full conversation history per session, retrievable by the user. | Past conversations are listed and their message history is fully retrievable. |
| FR-026 | SHOULD | Detect and report trends across multiple records of the same type over time (e.g., rising HbA1c, worsening tremor). | The system surfaces a trend alert when three or more data points show a consistent directional change. |
| FR-027 | MUST | Flag potential drug interactions across stored active prescriptions for a member. | When a new prescription is added, the system checks against active prescriptions and returns any interaction warnings. |
| FR-028 | MUST | Append a mandatory disclaimer to every AI-generated response: "This is not medical advice. Consult a healthcare professional." | Every AI response payload contains a non-empty `disclaimer` field with the exact disclaimer text. |
| FR-029 | MUST | Implement AI provider failover chain: Google Gemini 2.5 Flash → Groq → OpenRouter → Ollama Cloud → Ollama Local. Switch on rate-limit or quota exhaustion. | When the active provider returns a rate-limit or quota error, the system transparently retries with the next provider in the chain. |

### Reminders & Notifications

| ID | Priority | Statement | Acceptance Criterion |
|----|----------|-----------|----------------------|
| FR-030 | MUST | Create a reminder linked to a family member with type: upcoming appointment, medication, follow-up, check-up, or prescription refill. | The reminder is persisted with its type and appears in the member's reminder list. |
| FR-031 | MUST | Support flexible scheduling: daily, weekly, or custom interval (every N days). | The reminder fires at the correct interval as configured. |
| FR-032 | MUST | Deliver in-app notifications for due reminders. | A due reminder appears in the user's notification feed within the application. |
| FR-033 | COULD | Deliver email notifications for due reminders. | *Deferred to post-v1.* Placeholder interface is defined but not implemented. |

### Identity & Access Control

| ID | Priority | Statement | Acceptance Criterion |
|----|----------|-----------|----------------------|
| FR-034 | MUST | Authenticate users via username and password. | Login returns a session token; invalid credentials return 401. |
| FR-035 | MUST | Hash passwords using bcrypt or argon2. | Passwords are stored as hashes; plaintext is never persisted. |
| FR-036 | MUST | Enforce per-member access control: a user may only view/edit records of members they are authorised for. | A request to access an unauthorised member's records returns 403. |
| FR-037 | MUST | Maintain an immutable audit log of all data access and mutations (create, update, soft-delete). | Every mutation generates an audit entry with actor, action, target entity, and timestamp. Entries cannot be modified or deleted. |
| FR-038 | MUST | Validate uploaded files by MIME type (`application/pdf`, `image/jpeg`, `image/png`) and enforce a 25 MB size limit. | Invalid MIME or oversized uploads are rejected with 422 and a descriptive error. |
| FR-039 | MUST | Enforce rate limiting on API endpoints. | More than 100 requests per minute from a single session returns 429. |

---

## Non-Functional Requirements

| ID | Priority | Statement |
|----|----------|-----------|
| NFR-001 | MUST | **Response time**: API endpoints must respond within 500 ms for 95th percentile of requests (excluding AI calls, which are bound by provider latency). |
| NFR-002 | MUST | **Availability**: The self-hosted application targets 99% uptime when the host machine is running. |
| NFR-003 | MUST | **Data encryption at rest**: SQLite database encrypted via SQLCipher (AES-256). |
| NFR-004 | MUST | **Data encryption in transit**: All HTTP traffic served over TLS (via reverse proxy or direct). |
| NFR-005 | MUST | **Password strength**: Minimum 8 characters; enforce at least one uppercase, one digit, one special character. |
| NFR-006 | MUST | **Session management**: Session tokens expire after 24 hours of inactivity. |
| NFR-007 | MUST | **Input validation**: All user input validated via Pydantic v2 schemas; reject malformed data with 422. |
| NFR-008 | SHOULD | **Data retention**: Health records and audit logs are retained indefinitely unless explicitly soft-deleted by the user. |
| NFR-009 | MUST | **Deployment**: Application runs as a Docker Compose stack (app + database) on a single host. |
| NFR-010 | MUST | **Footprint**: Application container memory usage must not exceed 512 MB under normal load. |

---

## User Stories

| US | Role | Story | Links |
|----|------|-------|-------|
| US-001 | Household Admin | As a household admin, I want to create a household and add family members, so that each member has a dedicated health profile. | FR-001, FR-002, FR-003 |
| US-002 | Household Admin | As a household admin, I want to add doctors and clinics with contact details and UHIDs, so that provider information is centralised. | FR-004 |
| US-003 | Family Member | As a family member, I want to see my Brief Medical History and Active Medications on my dashboard, so that I have a quick health overview. | FR-005, FR-006 |
| US-004 | Family Member | As a family member, I want to add a doctor visit with all consultation details, so that my visit history is complete. | FR-010 |
| US-005 | Family Member | As a family member, I want to log lab test results, so that I can track diagnostic data over time. | FR-011 |
| US-006 | Family Member | As a family member, I want to track my blood glucose and HbA1c readings, so that I can monitor my diabetes management. | FR-012, FR-013 |
| US-007 | Family Member | As a family member, I want to store my eyeglass prescription, so that I have a record of my vision correction. | FR-014 |
| US-008 | Family Member | As a family member, I want to track Parkinson's symptom severity (tremor, stiffness), so that disease progression is documented. | FR-015 |
| US-009 | Family Member | As a family member, I want to attach scanned reports and photos to my health records, so that original documents are preserved. | FR-017 |
| US-010 | Family Member | As a family member, I want to view my health timeline chronologically and filter by type, keyword, or date, so that I can find specific records quickly. | FR-018, FR-019 |
| US-011 | Family Member | As a family member, I want to export my timeline as a PDF, so that I can share it with a doctor. | FR-020 |
| US-012 | Family Member | As a family member, I want to view all my lab results in a single table, so that I can compare tests over time. | FR-021 |
| US-013 | Family Member | As a family member, I want to get an AI-generated insight on a health record, so that I understand what the results mean in context. | FR-022, FR-023 |
| US-014 | Family Member | As a family member, I want to chat with the AI about my health data or general health topics, so that I can ask questions in plain language. | FR-024, FR-025 |
| US-015 | Family Member | As a family member, I want the AI to alert me to trends and drug interactions, so that I can take informed action. | FR-026, FR-027 |
| US-016 | Family Member | As a family member, I want every AI response to carry a "not medical advice" disclaimer, so that I do not mistake it for professional guidance. | FR-028 |
| US-017 | Family Member | As a family member, I want to create recurring reminders for medications and follow-ups, so that I do not miss important health tasks. | FR-030, FR-031, FR-032 |
| US-018 | Household Admin | As a household admin, I want to control which members each user can access, so that sensitive health data is kept private within the household. | FR-036 |
| US-019 | System Operator | As a system operator, I want to deploy the application via Docker Compose on my server, so that setup is repeatable and self-contained. | NFR-009 |

---

## Out of Scope (v1)

1. **Email notifications** — In-app notifications only for v1. Email delivery interface is defined but not implemented; deferred to a post-v1 iteration.
2. **Multi-household support** — Single household only. The architecture will use a single database per deployment, but the data model avoids household-hardcoded assumptions to ease future per-household DB isolation.
3. **EHR / hospital system integration** — No HL7, FHIR, or external system connectivity. All data entry is manual or via the structured questionnaire wizard.
4. **HIPAA certification** — The application uses strong encryption (SQLCipher, TLS) suitable for personal use but is not formally HIPAA-compliant.
5. **Telemedicine / appointment booking** — No video calls, scheduling integration, or doctor communication features.
6. **Insurance and billing** — No claim management, billing, or insurance tracking.
