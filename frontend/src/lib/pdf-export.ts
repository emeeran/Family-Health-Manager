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
 * back to a blob download (→ Downloads).
 */

const PAGE_MARGIN_MM = 10;

// html2canvas-pro ships loose types; treat the factory permissively.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Html2CanvasPro = (el: HTMLElement, opts?: any) => Promise<HTMLCanvasElement>;

function withPdfExt(filename: string): string {
  return filename.toLowerCase().endsWith(".pdf") ? filename : `${filename}.pdf`;
}

async function renderToPDF(element: HTMLElement, filename: string): Promise<void> {
  // Surface the actual failure (the desktop webview swallows console errors
  // and the call-site catch falls back to a no-op window.print()).
  const { toast } = await import("sonner");
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

    const pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const usableW = pageW - PAGE_MARGIN_MM * 2;
    const usableH = pageH - PAGE_MARGIN_MM * 2;

    // Each page maps to a fixed vertical slice of the source canvas.
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

    // Save: native Save-As dialog in the Tauri desktop shell; browser blob
    // download (to Downloads) elsewhere, or if the dialog/fs path is unavailable.
    let saved = false;
    let cancelled = false;
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
        if (path) {
          await writeFile(path, new Uint8Array(pdf.output("arraybuffer")));
          saved = true;
        } else {
          cancelled = true;
        }
      }
    } catch {
      // Not Tauri, or dialog/fs unavailable — fall back to a blob download below.
    }
    if (saved) {
      toast.success("PDF saved");
    } else if (!cancelled) {
      pdf.save(withPdfExt(filename));
      toast.success(`PDF saved — "${withPdfExt(filename)}" is in your Downloads folder`, {
        duration: 7000,
      });
    }
  } catch (err) {
    const msg = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
    toast.error(`PDF export failed — ${msg}`);
    throw err;
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
