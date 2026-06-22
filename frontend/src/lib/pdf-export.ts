/**
 * Shared PDF export utility using html2pdf.js.
 * Replaces window.print() / document.write() patterns with real PDF downloads.
 */

/**
 * Export a DOM element to a downloadable PDF file.
 */
export async function exportElementToPDF(element: HTMLElement, filename: string): Promise<void> {
  // Dynamic import — html2pdf.js is large and only needed on export
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const html2pdf: any = await import("html2pdf.js");

  const options = {
    margin: [10, 10, 10, 10],
    filename,
    image: { type: "jpeg", quality: 0.95 },
    html2canvas: { scale: 2, useCORS: true, logging: false },
    jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
    pagebreak: { mode: ["avoid-all", "css", "legacy"] },
  };

  await html2pdf(element, options);
}

/**
 * Export content by rendering it into a temporary container, generating PDF, then cleaning up.
 */
export async function exportHTMLToPDF(html: string, filename: string): Promise<void> {
  const container = document.createElement("div");
  container.innerHTML = html;
  container.style.cssText =
    "position:fixed;left:-9999px;top:0;width:210mm;padding:20px;font-family:system-ui,sans-serif;color:#000;background:#fff;";
  document.body.appendChild(container);

  try {
    await exportElementToPDF(container, filename);
  } finally {
    document.body.removeChild(container);
  }
}
