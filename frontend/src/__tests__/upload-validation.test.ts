import { describe, expect, it } from "vitest";
import { isAllowedUpload } from "@/lib/constants";

function file(name: string, type: string): File {
  return new File(["x"], name, { type });
}

describe("isAllowedUpload", () => {
  it("accepts files with a recognised MIME type", () => {
    expect(isAllowedUpload(file("scan.pdf", "application/pdf"))).toBe(true);
    expect(isAllowedUpload(file("photo.jpg", "image/jpeg"))).toBe(true);
    expect(isAllowedUpload(file("photo.png", "image/png"))).toBe(true);
    expect(isAllowedUpload(file("shot.webp", "image/webp"))).toBe(true);
  });

  it("accepts drag-dropped files whose MIME type the browser failed to sniff", () => {
    // Nautilus / other Linux file managers routinely hand the browser an empty
    // `file.type` for dragged files (especially PDFs). The previous MIME-only
    // check rejected these as "Invalid file type" → drag-drop "didn't work".
    expect(isAllowedUpload(file("report.pdf", ""))).toBe(true);
    expect(isAllowedUpload(file("report.PDF", ""))).toBe(true);
    expect(isAllowedUpload(file("photo.jpeg", ""))).toBe(true);
    expect(isAllowedUpload(file("shot.webp", ""))).toBe(true); // was missing from the extension set
  });

  it("rejects unsupported types and extensionless files", () => {
    expect(isAllowedUpload(file("notes.txt", "text/plain"))).toBe(false);
    expect(isAllowedUpload(file("malware.exe", "application/octet-stream"))).toBe(false);
    expect(isAllowedUpload(file("noext", ""))).toBe(false);
    expect(isAllowedUpload(file("invoice.pdf", "application/x-malware"))).toBe(false);
  });
});
