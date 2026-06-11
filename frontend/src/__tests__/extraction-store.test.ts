import {
  saveExtraction,
  loadExtraction,
  getBatchesForType,
  consumeBatch,
  clearExtraction,
  removeBatch,
} from "@/lib/extraction-store";

// Mock sessionStorage
const store: Record<string, string> = {};
const mockSessionStorage = {
  getItem: vi.fn((key: string) => store[key] ?? null),
  setItem: vi.fn((_key: string, value: string) => {
    store[_key] = value;
  }),
  removeItem: vi.fn((key: string) => {
    delete store[key];
  }),
  clear: vi.fn(() => {
    for (const key of Object.keys(store)) delete store[key];
  }),
  get length() {
    return Object.keys(store).length;
  },
  key: vi.fn((_: number) => null),
};

Object.defineProperty(globalThis, "sessionStorage", { value: mockSessionStorage });

beforeEach(() => {
  for (const key of Object.keys(store)) delete store[key];
  vi.clearAllMocks();
});

describe("extraction-store", () => {
  const memberId = "test-member-1";

  describe("saveExtraction + loadExtraction", () => {
    it("saves and loads a batch", () => {
      saveExtraction(memberId, {
        fileName: "test.pdf",
        transcription: null,
        prescriptions: [{ medicine: "Aspirin", dosage: "100mg" }],
        labTests: [],
        eyeglass: null,
        baseFields: { record_type: "doctor_visit" },
      });

      const loaded = loadExtraction(memberId);
      expect(loaded).not.toBeNull();
      expect(loaded!.batches).toHaveLength(1);
      expect(loaded!.batches[0].fileName).toBe("test.pdf");
      expect(loaded!.batches[0].prescriptions).toEqual([{ medicine: "Aspirin", dosage: "100mg" }]);
    });

    it("returns null when no data stored", () => {
      expect(loadExtraction(memberId)).toBeNull();
    });

    it("keeps only 3 batches max", () => {
      for (let i = 0; i < 5; i++) {
        saveExtraction(memberId, {
          fileName: `file${i}.pdf`,
          transcription: null,
          prescriptions: [],
          labTests: [],
          eyeglass: null,
          baseFields: {},
        });
      }

      const loaded = loadExtraction(memberId);
      expect(loaded!.batches).toHaveLength(3);
    });
  });

  describe("getBatchesForType", () => {
    it("filters by prescription type", () => {
      saveExtraction(memberId, {
        fileName: "rx.pdf",
        transcription: null,
        prescriptions: [{ medicine: "Test" }],
        labTests: [],
        eyeglass: null,
        baseFields: {},
      });
      saveExtraction(memberId, {
        fileName: "lab.pdf",
        transcription: null,
        prescriptions: [],
        labTests: [{ test_name: "CBC" }],
        eyeglass: null,
        baseFields: {},
      });

      expect(getBatchesForType(memberId, "prescriptions")).toHaveLength(1);
      expect(getBatchesForType(memberId, "labTests")).toHaveLength(1);
    });
  });

  describe("consumeBatch", () => {
    it("consumes and removes data from a batch", () => {
      saveExtraction(memberId, {
        fileName: "rx.pdf",
        transcription: null,
        prescriptions: [{ medicine: "Aspirin" }],
        labTests: [{ test_name: "CBC" }],
        eyeglass: null,
        baseFields: {},
      });

      const loaded = loadExtraction(memberId)!;
      const batchId = loaded.batches[0].id;

      const rx = consumeBatch(memberId, batchId, "prescriptions");
      expect(rx).toEqual([{ medicine: "Aspirin" }]);

      // Batch still exists because it has labTests
      const afterConsume = loadExtraction(memberId);
      expect(afterConsume).not.toBeNull();
    });

    it("removes batch when fully consumed", () => {
      saveExtraction(memberId, {
        fileName: "rx.pdf",
        transcription: null,
        prescriptions: [{ medicine: "Test" }],
        labTests: [],
        eyeglass: null,
        baseFields: {},
      });

      const batchId = loadExtraction(memberId)!.batches[0].id;
      consumeBatch(memberId, batchId, "prescriptions");

      expect(loadExtraction(memberId)).toBeNull();
    });
  });

  describe("removeBatch", () => {
    it("removes a specific batch by ID", () => {
      saveExtraction(memberId, {
        fileName: "a.pdf",
        transcription: null,
        prescriptions: [{ medicine: "A" }],
        labTests: [],
        eyeglass: null,
        baseFields: {},
      });

      const batchId = loadExtraction(memberId)!.batches[0].id;
      removeBatch(memberId, batchId);

      expect(loadExtraction(memberId)).toBeNull();
    });
  });

  describe("clearExtraction", () => {
    it("clears all data for a member", () => {
      saveExtraction(memberId, {
        fileName: "test.pdf",
        transcription: null,
        prescriptions: [],
        labTests: [],
        eyeglass: null,
        baseFields: {},
      });

      clearExtraction(memberId);
      expect(loadExtraction(memberId)).toBeNull();
    });
  });
});
