import type { RecordType } from "./types/enums";

export interface FieldDef {
  key: string;
  label: string;
  type: "text" | "number" | "textarea" | "select" | "date";
  placeholder?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
  step?: string;
  min?: string;
  max?: string;
  helpText?: string;
  span?: 1 | 2;
}

export interface TableRowDef {
  key: string;
  label: string;
  fields: FieldDef[];
  allowAddRemove?: boolean;
}

export interface SchemaFieldVisibility {
  diagnosis: boolean;
  prescription_text: boolean;
  next_review_date: boolean;
  provider_id: boolean;
  record_time: boolean;
}

export interface RecordTypeConfig {
  recordType: RecordType;
  schemaFields: SchemaFieldVisibility;
  customFields: FieldDef[];
  /** Single table (legacy) */
  tableRows?: TableRowDef;
  /** Multiple tables — takes precedence over tableRows */
  tables?: TableRowDef[];
  description?: string;
}

/** Get all table definitions from a config (handles both single and multi-table) */
export function getTables(config: RecordTypeConfig): TableRowDef[] {
  if (config.tables && config.tables.length > 0) return config.tables;
  if (config.tableRows) return [config.tableRows];
  return [];
}

const PRESCRIPTION_TABLE: TableRowDef = {
  key: "prescriptions",
  label: "Prescription",
  allowAddRemove: true,
  fields: [
    {
      key: "type",
      label: "Type",
      type: "select",
      options: [
        { value: "Tab", label: "Tab" },
        { value: "Cap", label: "Cap" },
        { value: "Inj", label: "Inj" },
        { value: "Syp", label: "Syp" },
        { value: "Cream", label: "Cream" },
        { value: "Drops", label: "Drops" },
        { value: "Inhaler", label: "Inhaler" },
        { value: "Other", label: "Other" },
      ],
    },
    { key: "medicine", label: "Medicine", type: "text", placeholder: "e.g. Syndopa 110" },
    { key: "dosage", label: "Dosage", type: "text", placeholder: "e.g. 1-1-1" },
    { key: "duration", label: "Duration", type: "text", placeholder: "e.g. 30 days" },
    {
      key: "timing",
      label: "Timing",
      type: "select",
      options: [
        { value: "before_food", label: "Before Food" },
        { value: "after_food", label: "After Food" },
        { value: "with_food", label: "With Food" },
        { value: "empty_stomach", label: "Empty Stomach" },
        { value: "bedtime", label: "Bedtime" },
        { value: "sos", label: "SOS" },
        { value: "stat", label: "Stat" },
      ],
    },
    { key: "note", label: "Note", type: "text", placeholder: "Optional note" },
  ],
};

const LAB_TEST_FIELDS: FieldDef[] = [
  { key: "test_name", label: "Test", type: "text", required: true, placeholder: "e.g. HbA1c" },
  { key: "result", label: "Result", type: "text", placeholder: "e.g. 8.9 %" },
  { key: "ref_value", label: "Ref. Value", type: "text", placeholder: "e.g. 6.0 %" },
  { key: "note", label: "Note", type: "text", placeholder: "e.g. High" },
];

const LAB_RESULTS_TABLE: TableRowDef = {
  key: "lab_results",
  label: "Lab Results",
  allowAddRemove: true,
  fields: LAB_TEST_FIELDS,
};

const DOCTOR_VISIT: RecordTypeConfig = {
  recordType: "doctor_visit",
  schemaFields: {
    diagnosis: true,
    prescription_text: false,
    next_review_date: true,
    provider_id: true,
    record_time: true,
  },
  customFields: [
    {
      key: "chief_complaint",
      label: "Chief Complaint",
      type: "textarea",
      required: true,
      placeholder: "Describe the main reason for the visit...",
      span: 2,
    },
    {
      key: "existing_conditions",
      label: "Existing Conditions",
      type: "text",
      placeholder: "e.g. T2DM, Hypertension, Depression",
      span: 2,
    },
    {
      key: "investigations",
      label: "Investigations",
      type: "textarea",
      placeholder: "Tests ordered or recommended...",
      span: 2,
    },
    {
      key: "notes",
      label: "Notes",
      type: "textarea",
      placeholder: "Additional observations, advice...",
      span: 2,
    },
  ],
  tables: [PRESCRIPTION_TABLE, LAB_RESULTS_TABLE],
  description: "Record details from a doctor consultation.",
};

const LAB_REPORT: RecordTypeConfig = {
  recordType: "lab_report",
  schemaFields: {
    diagnosis: false,
    prescription_text: false,
    next_review_date: false,
    provider_id: true,
    record_time: true,
  },
  customFields: [],
  tableRows: {
    key: "tests",
    label: "Test Results",
    allowAddRemove: true,
    fields: LAB_TEST_FIELDS,
  },
  description: "Record laboratory test results.",
};

const RX_EYEGLASS: RecordTypeConfig = {
  recordType: "rx_eyeglass",
  schemaFields: {
    diagnosis: false,
    prescription_text: false,
    next_review_date: true,
    provider_id: true,
    record_time: false,
  },
  customFields: [
    { key: "re_sph", label: "SPH (RE)", type: "text", placeholder: "e.g. +2.50" },
    { key: "re_cyl", label: "CYL (RE)", type: "text", placeholder: "e.g. -0.50" },
    { key: "re_axs", label: "AXS (RE)", type: "text", placeholder: "e.g. 140" },
    { key: "re_va", label: "VA (RE)", type: "text", placeholder: "e.g. 6/6" },
    { key: "le_sph", label: "SPH (LE)", type: "text", placeholder: "e.g. +1.25" },
    { key: "le_cyl", label: "CYL (LE)", type: "text", placeholder: "e.g. -0.75" },
    { key: "le_axs", label: "AXS (LE)", type: "text", placeholder: "e.g. 090" },
    { key: "le_va", label: "VA (LE)", type: "text", placeholder: "e.g. 6/6" },
    { key: "add_power", label: "ADD", type: "text", placeholder: "e.g. +2.50" },
    { key: "pd", label: "PD", type: "text", placeholder: "e.g. 32/32" },
  ],
  description: "Record an eyeglass prescription.",
};

const BLOOD_GLUCOSE: RecordTypeConfig = {
  recordType: "blood_glucose",
  schemaFields: {
    diagnosis: false,
    prescription_text: false,
    next_review_date: false,
    provider_id: false,
    record_time: true,
  },
  customFields: [
    {
      key: "glucose_value",
      label: "Glucose Value",
      type: "number",
      required: true,
      placeholder: "e.g. 120",
      min: "20",
      max: "600",
      helpText: "mg/dL",
    },
    {
      key: "meal_timing",
      label: "Meal Timing",
      type: "select",
      required: true,
      options: [
        { value: "before_food", label: "Before Food" },
        { value: "after_food", label: "After Food" },
      ],
    },
    {
      key: "insulin_dose",
      label: "Insulin Dose",
      type: "number",
      placeholder: "e.g. 10",
      min: "0",
      max: "100",
      helpText: "units",
    },
    {
      key: "insulin_type",
      label: "Insulin Type",
      type: "select",
      options: [
        { value: "rapid", label: "Rapid-acting" },
        { value: "short", label: "Short-acting" },
        { value: "intermediate", label: "Intermediate" },
        { value: "long", label: "Long-acting" },
        { value: "mixed", label: "Mixed / Pre-mixed" },
      ],
    },
    {
      key: "carbs_consumed",
      label: "Carbs Consumed",
      type: "number",
      placeholder: "e.g. 45",
      min: "0",
      max: "500",
      helpText: "grams",
    },
    {
      key: "notes",
      label: "Notes",
      type: "textarea",
      placeholder: "Any observations...",
      span: 2,
    },
  ],
  description: "Record a blood glucose reading.",
};

const HBA1C: RecordTypeConfig = {
  recordType: "hba1c",
  schemaFields: {
    diagnosis: false,
    prescription_text: false,
    next_review_date: false,
    provider_id: false,
    record_time: true,
  },
  customFields: [
    {
      key: "hba1c_value",
      label: "HbA1c Value",
      type: "number",
      required: true,
      placeholder: "e.g. 6.5",
      min: "2",
      max: "20",
      step: "0.1",
      helpText: "%",
    },
    {
      key: "test_type",
      label: "Test Type",
      type: "select",
      required: false,
      options: [
        { value: "routine", label: "Routine Checkup" },
        { value: "diagnostic", label: "Diagnostic" },
      ],
    },
  ],
  description: "Record an HbA1c (glycated hemoglobin) reading.",
};

const MISC_RECORD: RecordTypeConfig = {
  recordType: "misc_record",
  schemaFields: {
    diagnosis: true,
    prescription_text: false,
    next_review_date: false,
    provider_id: true,
    record_time: false,
  },
  customFields: [],
  description: "Record any other health-related information.",
};

const SEVERITY_OPTIONS = [
  { value: "none", label: "None" },
  { value: "mild", label: "Mild" },
  { value: "moderate", label: "Moderate" },
  { value: "severe", label: "Severe" },
];

const PARKINSONS_LOG: RecordTypeConfig = {
  recordType: "parkinsons_log",
  schemaFields: {
    diagnosis: false,
    prescription_text: false,
    next_review_date: false,
    provider_id: false,
    record_time: true,
  },
  customFields: [
    {
      key: "motor_state",
      label: "Motor State",
      type: "select",
      required: true,
      options: [
        { value: "on", label: "ON — Good mobility" },
        { value: "off", label: "OFF — Reduced mobility" },
        { value: "wearing_off", label: "Wearing Off — Medication fading" },
        { value: "dyskinesia", label: "Dyskinesia — Involuntary movements" },
      ],
    },
    {
      key: "tremor_severity",
      label: "Tremor",
      type: "select",
      options: SEVERITY_OPTIONS,
    },
    {
      key: "rigidity",
      label: "Rigidity / Stiffness",
      type: "select",
      options: SEVERITY_OPTIONS,
    },
    {
      key: "bradykinesia",
      label: "Slowness of Movement",
      type: "select",
      options: SEVERITY_OPTIONS,
    },
    {
      key: "gait_balance",
      label: "Gait & Balance",
      type: "select",
      options: [
        { value: "normal", label: "Normal" },
        { value: "mild", label: "Mild Impairment" },
        { value: "moderate", label: "Moderate" },
        { value: "severe", label: "Severe / Freezing" },
      ],
    },
    {
      key: "mood",
      label: "Mood",
      type: "select",
      options: [
        { value: "good", label: "Good" },
        { value: "fair", label: "Fair" },
        { value: "low", label: "Low" },
        { value: "anxious", label: "Anxious" },
      ],
    },
    {
      key: "sleep_quality",
      label: "Sleep Quality",
      type: "select",
      options: [
        { value: "good", label: "Good" },
        { value: "fair", label: "Fair" },
        { value: "poor", label: "Poor" },
        { value: "insomnia", label: "Insomnia" },
      ],
    },
    {
      key: "notes",
      label: "Notes",
      type: "textarea",
      placeholder: "e.g. Stiffness worse in morning, difficulty turning in bed...",
      span: 2,
    },
  ],
  description: "Log Parkinson's Disease symptoms and motor state.",
};

export const RECORD_TYPE_CONFIGS: Record<RecordType, RecordTypeConfig> = {
  doctor_visit: DOCTOR_VISIT,
  lab_report: LAB_REPORT,
  rx_eyeglass: RX_EYEGLASS,
  blood_glucose: BLOOD_GLUCOSE,
  hba1c: HBA1C,
  misc_record: MISC_RECORD,
  vitals: MISC_RECORD,
  parkinsons_log: PARKINSONS_LOG,
};

export function getConfig(recordType: RecordType): RecordTypeConfig {
  return RECORD_TYPE_CONFIGS[recordType];
}
