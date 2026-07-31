/**
 * Shared PDF export utility.
 *
 * Uses `html2canvas-pro` (a CSS Color 4 / `oklch()`-aware fork) + `jsPDF`.
 * This replaces `html2pdf.js`, whose bundled `html2canvas` cannot parse the
 * `oklch()` colors Tailwind v4 emits for utility classes — it threw on any
 * themed element, the export caught it, fell back to `window.print()` (a no-op
 * in the Tauri webview), and PDF export silently did nothing.
 *
 * The element is rasterized once, then sliced into A4 pages. In the Tauri
 * desktop shell a native Save-As dialog writes the file; in a browser it falls
 * back to a blob download (→ Downloads). Failures are surfaced via a sonner
 * toast and NOT re-thrown, so callers don't double-signal by opening print.
 */

const PAGE_MARGIN_MM = 10;

// html2canvas-pro ships loose types; treat the factory permissively.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Html2CanvasPro = (el: HTMLElement, opts?: any) => Promise<HTMLCanvasElement>;

function withPdfExt(filename: string): string {
  return filename.toLowerCase().endsWith(".pdf") ? filename : `${filename}.pdf`;
}

function errMsg(err: unknown): string {
  return err instanceof Error ? `${err.name}: ${err.message}` : String(err);
}

async function renderToPDF(element: HTMLElement, filename: string): Promise<void> {
  const { toast } = await import("sonner");

  // 1. Render the element to a paginated PDF.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let pdf: any;
  try {
    const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
      import("html2canvas-pro"),
      import("jspdf"),
    ]);

    const canvas = await (html2canvas as Html2CanvasPro)(element, {
      scale: 2,
      useCORS: true,
      logging: false,
      backgroundColor: "#ffffff",
    });

    pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const usableW = pageW - PAGE_MARGIN_MM * 2;
    const usableH = pageH - PAGE_MARGIN_MM * 2;
    const pxPerMm = canvas.width / usableW;
    const slicePx = Math.max(1, Math.floor(usableH * pxPerMm));

    for (let y = 0, page = 0; y < canvas.height; y += slicePx, page++) {
      const sliceH = Math.min(slicePx, canvas.height - y);
      const pageCanvas = document.createElement("canvas");
      pageCanvas.width = canvas.width;
      pageCanvas.height = sliceH;
      const ctx = pageCanvas.getContext("2d");
      if (!ctx) break;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, pageCanvas.width, pageCanvas.height);
      ctx.drawImage(canvas, 0, y, canvas.width, sliceH, 0, 0, canvas.width, sliceH);
      const imgData = pageCanvas.toDataURL("image/jpeg", 0.95);
      if (page > 0) pdf.addPage();
      pdf.addImage(imgData, "JPEG", PAGE_MARGIN_MM, PAGE_MARGIN_MM, usableW, sliceH / pxPerMm);
    }
  } catch (err) {
    // Own the failure UX; do NOT re-throw — callers wrap this in
    // `try { ... } catch { window.print() }` and a throw would double-signal.
    toast.error(`PDF export failed — ${errMsg(err)}`);
    return;
  }

  // 2. Save: native Save-As in the Tauri desktop shell; browser blob download
  //    (→ Downloads) elsewhere, or if the Tauri APIs are unavailable.
  try {
    const isTauri = (await import("@tauri-apps/api/core")).isTauri();
    if (isTauri) {
      const [{ save }, { writeFile }] = await Promise.all([
        import("@tauri-apps/plugin-dialog"),
        import("@tauri-apps/plugin-fs"),
      ]);
      const path = await save({
        defaultPath: withPdfExt(filename),
        filters: [{ name: "PDF", extensions: ["pdf"] }],
      });
      if (!path) return; // user cancelled the dialog — silent
      try {
        await writeFile(path, new Uint8Array(pdf.output("arraybuffer")));
        toast.success("PDF saved");
      } catch (werr) {
        // A real write failure (permissions, disk full) — don't silently dump
        // to Downloads; tell the user the chosen location didn't work.
        toast.error(`Couldn't write PDF to the chosen location — ${errMsg(werr)}`);
      }
      return;
    }
  } catch {
    // Not Tauri, or the dialog/fs plugins are unavailable — fall back below.
  }

  try {
    pdf.save(withPdfExt(filename));
    toast.success(`PDF saved — "${withPdfExt(filename)}" is in your Downloads folder`, {
      duration: 7000,
    });
  } catch (err) {
    toast.error(`PDF export failed — ${errMsg(err)}`);
  }
}

/**
 * Export a DOM element to a downloadable PDF file.
 */
export async function exportElementToPDF(element: HTMLElement, filename: string): Promise<void> {
  await renderToPDF(element, filename);
}

/**
 * Export content by rendering it into a temporary container, generating the PDF,
 * then cleaning up.
 */
export async function exportHTMLToPDF(html: string, filename: string): Promise<void> {
  const container = document.createElement("div");
  container.innerHTML = html;
  container.style.cssText =
    "position:fixed;left:-9999px;top:0;width:210mm;padding:20px;font-family:system-ui,sans-serif;color:#000;background:#fff;";
  document.body.appendChild(container);

  try {
    await renderToPDF(container, filename);
  } finally {
    document.body.removeChild(container);
  }
}
