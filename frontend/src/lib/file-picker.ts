/**
 * Cross-runtime file picker.
 *
 * In the Tauri desktop webview, `<input type="file">` does not open a native
 * file dialog (tauri#3014 — Tauri doesn't wire the webview file-chooser, most
 * visibly on Linux/WebKit2GTK). So under Tauri we route through
 * `@tauri-apps/plugin-dialog` `open()` and read each chosen file's bytes via
 * `@tauri-apps/plugin-fs`, returning the same `File[]` shape the rest of the
 * app already consumes (validation, multipart upload, AI extraction).
 *
 * In a browser / `vite dev`, it falls back to a transient `<input type=file>`.
 *
 * Mirrors the dynamic-import pattern in `pdf-export.ts` so the Tauri plugins
 * stay out of the browser bundle.
 */

export interface PickFilesOptions {
  /** Allow choosing more than one file. */
  multiple?: boolean;
  /** Extensions (no leading dot) that drive the OS dialog filter. */
  extensions?: string[];
  /** Pick a directory and return every matching file within it, recursively. */
  directory?: boolean;
}

const MIME_BY_EXT: Record<string, string> = {
  pdf: "application/pdf",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  zip: "application/zip",
};

function mimeForName(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  return MIME_BY_EXT[ext] ?? "";
}

function matchesExtensions(path: string, extensions?: string[]): boolean {
  if (!extensions?.length) return true;
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return extensions.includes(ext);
}

function normalizeSelection(sel: string | string[] | null): string[] {
  if (!sel) return [];
  return Array.isArray(sel) ? sel.filter(Boolean) : [sel];
}

/** Read a single on-disk path into a browser `File` (bytes + name + MIME). */
async function fileFromPath(
  path: string,
  readFile: (p: string) => Promise<Uint8Array>,
  basename: (p: string) => Promise<string>
): Promise<File> {
  const bytes = await readFile(path);
  // basename in @tauri-apps/api/path is async.
  const name = await basename(path).catch(() => path.split(/[\\/]/).pop() ?? path);
  // Copy into a dedicated ArrayBuffer: readFile returns a Uint8Array view whose
  // ArrayBufferLike-typed buffer isn't assignable to BlobPart under lib.dom
  // (SharedArrayBuffer union), and we want the File to own standalone bytes.
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return new File([buffer], name, { type: mimeForName(name) });
}

/** Tauri: native dialog + fs read. */
async function pickTauri({ multiple, extensions, directory }: PickFilesOptions): Promise<File[]> {
  const [{ open }, { readFile, readDir }, { basename, join }] = await Promise.all([
    import("@tauri-apps/plugin-dialog"),
    import("@tauri-apps/plugin-fs"),
    import("@tauri-apps/api/path"),
  ]);

  const openOpts: {
    multiple: boolean;
    directory: boolean;
    filters?: { name: string; extensions: string[] }[];
  } = { multiple: multiple ?? false, directory: directory ?? false };
  if (extensions?.length) {
    openOpts.filters = [{ name: "Allowed files", extensions }];
  }

  const selected = (await open(openOpts)) as string | string[] | null;
  const paths = normalizeSelection(selected);
  if (!paths.length) return [];

  // Directory mode ignores the filter; walk each directory recursively and
  // filter by extension ourselves (plugin-fs readDir is non-recursive + its
  // DirEntry carries only `name`, so we rebuild full paths with `join`).
  if (directory) {
    const collected: string[] = [];
    const walk = async (dir: string) => {
      const entries = await readDir(dir);
      for (const e of entries) {
        const full = await join(dir, e.name);
        if (e.isDirectory) {
          await walk(full);
        } else if (e.isSymlink) {
          continue; // skip symlinks to avoid loops / unexpected reads
        } else if (matchesExtensions(full, extensions)) {
          collected.push(full);
        }
      }
    };
    for (const dir of paths) await walk(dir);
    return Promise.all(collected.map((p) => fileFromPath(p, readFile, basename)));
  }

  return Promise.all(paths.map((p) => fileFromPath(p, readFile, basename)));
}

/** Browser/dev: transient hidden input. Resolves [] on cancel. */
function pickBrowser({ multiple, extensions, directory }: PickFilesOptions): Promise<File[]> {
  return new Promise<File[]>((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    if (multiple) input.multiple = true;
    if (extensions?.length) {
      input.accept = extensions.map((e) => `.${e}`).join(",");
    }
    if (directory) input.setAttribute("webkitdirectory", "");

    let settled = false;
    const finish = (files: File[]) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("focus", onFocus);
      input.remove();
      resolve(files);
    };
    // If the dialog is dismissed without a pick, the window regains focus while
    // the input still has no value. Give the `change` event a beat to land first
    // (some browsers fire focus slightly before change).
    const onFocus = () => {
      window.setTimeout(() => {
        if (!settled && !input.value) finish([]);
      }, 300);
    };

    input.addEventListener("change", () => {
      finish(Array.from(input.files ?? []));
    });
    input.style.display = "none";
    window.addEventListener("focus", onFocus);
    document.body.appendChild(input);
    input.click();
  });
}

/**
 * Open a file-selection dialog and return the chosen files.
 *
 * Returns `[]` (never throws) when the user cancels, so callers can do
 * `const files = await pickFiles(...); if (files.length) handle(files);`.
 */
export async function pickFiles(opts: PickFilesOptions = {}): Promise<File[]> {
  const { isTauri } = await import("@tauri-apps/api/core");
  return isTauri() ? pickTauri(opts) : pickBrowser(opts);
}
