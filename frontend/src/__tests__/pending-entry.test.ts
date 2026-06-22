import { setPendingEntry, consumePendingEntry, peekPendingEntry } from "@/lib/pending-entry";

describe("pending-entry singleton", () => {
  it("stores, peeks, and consumes a text entry exactly once", () => {
    setPendingEntry({ text: "BP 120/80 today" });
    expect(peekPendingEntry()?.text).toBe("BP 120/80 today");
    const consumed = consumePendingEntry();
    expect(consumed?.text).toBe("BP 120/80 today");
    expect(consumePendingEntry()).toBeNull();
  });

  it("stores and consumes a File entry (Files are not URL-serializable)", () => {
    const file = new File(["x"], "scan.pdf", { type: "application/pdf" });
    setPendingEntry({ file });
    expect(consumePendingEntry()?.file).toBe(file);
    expect(peekPendingEntry()).toBeNull();
  });

  it("peek does not clear the entry", () => {
    setPendingEntry({ text: "hello" });
    expect(peekPendingEntry()?.text).toBe("hello");
    expect(peekPendingEntry()?.text).toBe("hello");
    consumePendingEntry();
  });
});
