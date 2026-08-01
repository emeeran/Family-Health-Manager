import { describe, it, expect, beforeEach, vi } from "vitest";

/**
 * pickFiles() routes through @tauri-apps/plugin-dialog under Tauri and a
 * transient <input> in the browser. We mock the four Tauri modules (hoisted so
 * they exist before the dynamic imports resolve) and drive both branches.
 */
const mocks = vi.hoisted(() => ({
  open: vi.fn(),
  readFile: vi.fn(),
  readDir: vi.fn(),
  basename: vi.fn(),
  join: vi.fn(),
  tauri: false,
}));

vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => mocks.tauri }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open }));
vi.mock("@tauri-apps/plugin-fs", () => ({
  readFile: mocks.readFile,
  readDir: mocks.readDir,
}));
vi.mock("@tauri-apps/api/path", () => ({
  basename: mocks.basename,
  join: mocks.join,
}));

import { pickFiles } from "../file-picker";

const enc = (s: string) => new TextEncoder().encode(s);

beforeEach(() => {
  mocks.open.mockReset();
  mocks.readFile.mockReset();
  mocks.readDir.mockReset();
  mocks.basename.mockReset();
  mocks.join.mockReset();
  mocks.tauri = false;
});

describe("pickFiles — Tauri branch", () => {
  beforeEach(() => {
    mocks.tauri = true;
    mocks.basename.mockImplementation((p: string) => Promise.resolve(p.split("/").pop() ?? p));
  });

  it("returns File[] from dialog-selected paths with names + MIME", async () => {
    mocks.open.mockResolvedValue(["/home/u/a.pdf", "/tmp/b.jpg"]);
    mocks.readFile.mockImplementation((p: string) => Promise.resolve(enc(`bytes:${p}`)));

    const files = await pickFiles({
      multiple: true,
      extensions: ["pdf", "jpg", "jpeg", "png", "webp"],
    });

    expect(files.map((f) => f.name)).toEqual(["a.pdf", "b.jpg"]);
    expect(files[0].type).toBe("application/pdf");
    expect(files[1].type).toBe("image/jpeg");
    expect(files[0].size).toBe(enc("bytes:/home/u/a.pdf").length);
    expect(mocks.open).toHaveBeenCalledWith({
      multiple: true,
      directory: false,
      filters: [{ name: expect.any(String), extensions: ["pdf", "jpg", "jpeg", "png", "webp"] }],
    });
  });

  it("resolves [] when the dialog is cancelled (null)", async () => {
    mocks.open.mockResolvedValue(null);
    expect(await pickFiles({})).toEqual([]);
  });

  it("resolves [] when a single path isn't chosen (empty)", async () => {
    mocks.open.mockResolvedValue("");
    expect(await pickFiles({})).toEqual([]);
  });

  it("walks directories recursively and filters by extension (skips symlinks)", async () => {
    mocks.open.mockResolvedValue("/scans");
    mocks.join.mockImplementation((...parts: string[]) => Promise.resolve(parts.join("/")));
    mocks.readDir.mockImplementation(async (dir: string) => {
      if (dir === "/scans")
        return [
          { name: "a.pdf", isDirectory: false, isFile: true, isSymlink: false },
          { name: "sub", isDirectory: true, isFile: false, isSymlink: false },
          { name: "c.jpg", isDirectory: false, isFile: true, isSymlink: false },
          { name: "link.pdf", isDirectory: false, isFile: false, isSymlink: true },
        ];
      if (dir === "/scans/sub")
        return [
          { name: "b.txt", isDirectory: false, isFile: true, isSymlink: false },
          { name: "d.pdf", isDirectory: false, isFile: true, isSymlink: false },
        ];
      return [];
    });
    mocks.readFile.mockResolvedValue(enc("x"));

    const files = await pickFiles({ directory: true, extensions: ["pdf", "jpg"] });

    // b.txt filtered out (extension); link.pdf skipped (symlink); sub/d.pdf found via recursion.
    expect(files.map((f) => f.name).sort()).toEqual(["a.pdf", "c.jpg", "d.pdf"]);
    expect(mocks.readDir).toHaveBeenCalledWith("/scans");
    expect(mocks.readDir).toHaveBeenCalledWith("/scans/sub");
  });

  it("omits the filter when no extensions are given", async () => {
    mocks.open.mockResolvedValue([]);
    await pickFiles({});
    expect(mocks.open).toHaveBeenCalledWith({ multiple: false, directory: false });
  });
});

describe("pickFiles — browser branch", () => {
  /** Spy createElement so we can grab the transient input and drive it in jsdom. */
  function captureInput(): { input: () => HTMLInputElement | undefined; restore: () => void } {
    const created: HTMLInputElement[] = [];
    const real = document.createElement.bind(document);
    const spy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = real(tag);
      if (tag.toLowerCase() === "input") created.push(el as HTMLInputElement);
      return el;
    });
    return { input: () => created[0], restore: () => spy.mockRestore() };
  }

  it("resolves File[] when the input change fires", async () => {
    const { input, restore } = captureInput();
    const promise = pickFiles({ multiple: true, extensions: ["pdf"] });

    // wait for the transient input to be created + clicked
    await vi.waitFor(() => expect(input()).toBeTruthy());
    const el = input()!;
    expect(el.multiple).toBe(true);
    expect(el.accept).toBe(".pdf");

    const f = new File(["data"], "x.pdf", { type: "application/pdf" });
    Object.defineProperty(el, "files", { value: [f], configurable: true });
    el.dispatchEvent(new Event("change"));

    expect(await promise).toEqual([f]);
    restore();
  });

  it("resolves [] when the dialog is dismissed (window focus, empty value)", async () => {
    const { input, restore } = captureInput();
    const promise = pickFiles({});

    // Wait until pickBrowser has created the input + attached the focus listener
    // (pickFiles awaits the dynamic isTauri() import before that), THEN simulate
    // the OS dialog being dismissed without a pick.
    await vi.waitFor(() => expect(input()).toBeTruthy());
    window.dispatchEvent(new Event("focus"));
    // the focus handler waits 300ms before concluding it was a cancel
    await new Promise((r) => setTimeout(r, 400));

    expect(await promise).toEqual([]);
    restore();
  });
});
