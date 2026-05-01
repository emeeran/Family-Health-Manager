# Domain Analysis — Family Health Tracker

> Phase p0 — Domain-Driven Design decomposition of `raw_idea.txt`.

---

## 1. Bounded Contexts

### 1.1 Household Management

| Attribute      | Value |
|----------------|-------|
| **Name**       | Household Management |
| **Responsibility** | Create and manage households, family member profiles, intra-household relationships, and the healthcare provider directory (doctors, clinics, UHIDs, contact numbers). |
| **Owned Data** | Household, FamilyMember, Relationship, Provider (doctor/clinic), ProviderContact, UHIDMapping |

### 1.2 Health Records

| Attribute      | Value |
|----------------|-------|
| **Name**       | Health Records |
| **Responsibility** | Store, organise, and retrieve all types of medical data entries per family member. Manage file attachments, maintain the chronological timeline, and support search, filter, and PDF export. |
| **Owned Data** | HealthRecord (polymorphic root), LabResult, Prescription, DoctorVisit, ImagingReport, Vaccination, VitalSigns, AllergyEntry, ConditionEntry, FileAttachment, Timeline (read-model) |

Specialised tracking views (blood glucose, HbA1c, Parkinson's symptoms, eyeglass prescriptions) are query projections over typed HealthRecords — not separate entities.

### 1.3 AI Health Intelligence

| Attribute      | Value |
|----------------|-------|
| **Name**       | AI Health Intelligence |
| **Responsibility** | Generate plain-language insights from health data, explain selected records, power multi-turn conversational Q&A, detect trends across time-series records, and flag drug interactions. |
| **Owned Data** | Insight, Conversation, Message, TrendAnalysis, DrugInteractionAlert, DisclaimerLog |

### 1.4 Reminders & Notifications

| Attribute      | Value |
|----------------|-------|
| **Name**       | Reminders & Notifications |
| **Responsibility** | Create, schedule, and deliver recurring health reminders per family member (medications, follow-ups, check-ups, prescription refills). Manage notification preferences. |
| **Owned Data** | Reminder, ReminderSchedule, Notification, NotificationPreference |

### 1.5 Identity & Access Control

| Attribute      | Value |
|----------------|-------|
| **Name**       | Identity & Access Control |
| **Responsibility** | Authenticate users, enforce per-member access control within a household, maintain an immutable audit log, handle session management, and enforce rate limiting. |
| **Owned Data** | UserAccount, Session, AccessPolicy, AuditLogEntry, EncryptionKey (reference) |

---

## 2. Ubiquitous Language Glossary

| Term | Definition |
|------|-----------|
| **Household** | The primary organisational unit representing a single family residence and all its members. |
| **Family Member** | An individual within a household who owns health records; may also be a user with login credentials. |
| **User Account** | A login identity that grants access to the application; mapped to one or more family members. |
| **Provider** | A healthcare professional or clinic, including their contact details and UHID associations. |
| **UHID** | Unique Hospital/Health ID — an identifier assigned by a specific provider to a family member. |
| **Health Record** | A single, dated medical entry belonging to a family member; the root entity of all clinical data. |
| **Lab Result** | A health record capturing a diagnostic test, its result value, the performing lab, and the referring doctor. |
| **Prescription** | A health record capturing a medication order: medicine name, strength, dose, duration, and prescribing doctor. |
| **Doctor Visit** | A health record capturing a consultation: date, provider, chief complaint, findings, and advice. |
| **Imaging Report** | A health record capturing radiology or other imaging findings. |
| **Vaccination** | A health record capturing an immunisation event: vaccine name, date, batch, and administering provider. |
| **Vital Signs** | A health record capturing physiological measurements (blood pressure, glucose, weight, etc.) at a point in time. |
| **Allergy Entry** | A health record documenting a known allergen and the severity/type of reaction. |
| **Condition Entry** | A health record documenting a diagnosed chronic or acute condition. |
| **File Attachment** | A binary file (PDF, JPEG, PNG) linked to a health record, such as a scanned report or photo. |
| **Timeline** | A chronological, read-ordered list of all health records for a family member. |
| **Brief Medical History** | A summary view of a member's key conditions, allergies, and active medications. |
| **Active Medications** | A filtered view of current prescriptions presented as: Medicine & Strength — Dose — Duration — Prescribed by. |
| **Insight** | An AI-generated analysis of one or more health records, contextualised by past medical history. |
| **Conversation** | A persisted, multi-turn chat session between a user and the AI about health data. |
| **Trend Analysis** | An AI-identified pattern across multiple health records over time (e.g., rising cholesterol). |
| **Drug Interaction Alert** | An AI-flagged potential interaction between two or more stored prescriptions. |
| **Disclaimer** | A mandatory notice appended to every AI response stating it is not medical advice. |
| **Reminder** | A scheduled, recurring health prompt linked to a family member (medication, follow-up, check-up, refill). |
| **Notification** | A delivered instance of a reminder, via in-app display (and future email). |
| **Audit Log Entry** | An immutable record of who accessed or modified what data and when. |
| **Access Policy** | A rule defining which family members a user may view or edit. |

---

## 3. Core Aggregates

### 3.1 Household Aggregate

| Attribute | Value |
|-----------|-------|
| **Root Entity** | Household |
| **Child Entities** | FamilyMember, Provider |
| **Invariants** | 1. A household must contain at least one family member at all times. |
|               | 2. Each family member has a unique display name within the household. |
|               | 3. A provider must have at least one contact method (phone or address). |

### 3.2 Health Record Aggregate

| Attribute | Value |
|-----------|-------|
| **Root Entity** | HealthRecord |
| **Child Entities** |  DoctorVisit, LabResult, Prescription, ImagingReport, Vaccination, VitalSigns, AllergyEntry, ConditionEntry, FileAttachment |
| **Invariants** | 1. Every health record must reference exactly one family member. |
|               | 2. Every health record must have a recorded date. |
|               | 3. Every health record must have a type from the defined enum. |
|               | 4. File attachments must pass MIME-type validation and size limits. |
|               | 5. Records are append-only; deletion is a soft-delete that preserves the audit trail. |

### 3.3 AI Conversation Aggregate

| Attribute | Value |
|-----------|-------|
| **Root Entity** | Conversation |
| **Child Entities** | Message |
| **Invariants** | 1. A conversation must be associated with exactly one family member (or be a general-health chat). |
|               | 2. Every AI-generated message must include the mandatory disclaimer. |
|               | 3. Conversation history is immutable once persisted — messages cannot be edited or deleted. |

### 3.4 Reminder Aggregate

| Attribute | Value |
|-----------|-------|
| **Root Entity** | Reminder |
| **Child Entities** | ReminderSchedule |
| **Invariants** | 1. A reminder must belong to exactly one family member. |
|               | 2. A reminder must have a schedule (daily, weekly, or custom interval). |
|               | 3. A reminder must have a type from: up coming appointment, medication, follow-up, check-up, prescription refill. |

### 3.5 Audit Log Aggregate

| Attribute | Value |
|-----------|-------|
| **Root Entity** | AuditLogEntry |
| **Child Entities** | *(none — flat log)* |
| **Invariants** | 1. Audit log entries are strictly append-only — never updated or deleted. |
|               | 2. Every entry must record actor, action, target entity, and timestamp. |

---

## 4. Assumptions & Gaps

> Every item below requires clarification before proceeding to p1 (Requirements).

1. ⚠️ **NEEDS_CLARIFICATION**: What specific fields are required for each health record sub-type (e.g., blood glucose fields vs. HbA1c fields vs. eyeglass prescription fields)?

    1. Doctor Visit:
        Date, Cheif Complaint, Consultant, Investigations, Diagnosis, Prescription, Note, Next review
    2. LAB Test:
        Date, Test Name, Result, Note/Insight
    3. HbA1c Tracking:
        Date, Result, eBG, Note
    4. Blood Glucose:
       Date, Time, Before/After Food, Vlaue
    5. Eyeglass Prescription:
        Date, Doctor
        RE  SPH +0.00 CYL -0.00 AXS 180 
        LE  SPH +0.00 CYL -0.00 AXS 180
        ADD +2.50   PD RE 32 LE 31


2. ⚠️ **NEEDS_CLARIFICATION**: What is the maximum file attachment size, and which MIME types are permitted beyond PDF, JPEG, and PNG?

    Max size 25 MB, MIME types PDF, JPEG, PNG, JPG


3. ⚠️ **NEEDS_CLARIFICATION**: How should AI provider failover work? The raw idea lists Google → Groq → OpenRouter → Ollama Cloud → Ollama Local — is this an ordered fallback chain, automatic selection, or user-configurable?

    Default provider google gemini with model gemini 2.5 flash, it fails fallback to groq, then to openrouter etc. competent model with max tokens to be selected by AI. To use provider's free tier, upon hitting limit, fallback to another provder.

4. ⚠️ **NEEDS_CLARIFICATION**: What specific Parkinson's Disease symptoms should be tracked (tremor severity, UPDRS score, gait analysis, medication on/off periods)?

    track symptom severity like tremor, stiffness

5. ⚠️ **NEEDS_CLARIFICATION**: Is the general-health chatbot a separate conversation type, or does it share the same Conversation aggregate with a `scope: general | member` discriminator?

    chatbot to have an option to chat about paticular member's health or general issues


6. ⚠️ **NEEDS_CLARIFICATION**: What authentication method for the initial single-household version (username/password, OIDC, Tailscale-auth)?

    initial single-household version, username/password

7. ⚠️ **NEEDS_CLARIFICATION**: "Obtain complete medical history when adding new member" — does this imply a bulk-import wizard, a structured questionnaire, or manual entry?

    a structured questionnaire

8. ⚠️ **NEEDS_CLARIFICATION**: What email service should be used for future email notification delivery?

    later on can be added

9. ⚠️ **NEEDS_CLARIFICATION**: What encryption standard is expected for data at rest (application-level encryption, LUKS disk encryption, or SQLite SQLCipher)?

    AI to decide

10. ⚠️ **NEEDS_CLARIFICATION**: For multi-household support in the future, should household isolation be logical (same DB, tenant ID) or physical (separate databases)?

    separate databases