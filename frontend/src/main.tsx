import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { SWRConfig } from "swr";
import { ThemeProvider } from "next-themes";
import { toast } from "sonner";
import { router } from "./router";
import { ErrorBoundary } from "./components/shared/error-boundary";
import { ServiceWorkerRegistrar } from "./components/shared/register-sw";
import { ApiError } from "./lib/api-client";
import { initWebVitals } from "./lib/web-vitals";
import "./globals.css";

// Initialize Web Vitals tracking (logs to console in dev mode)
initWebVitals();

// Surface server/network errors globally so a component that forgets to read
// its SWR `error` field doesn't render a silent blank screen. Auth (401) and
// client (4xx) errors are left to inline handlers; only infrastructure
// failures (5xx, network) get a toast.
const handleSwrError = (err: unknown) => {
  if (err instanceof ApiError) {
    if (err.status >= 500 || err.status === 0) {
      toast.error(err.data?.message || "Server error");
    }
    return;
  }
  toast.error(err instanceof Error ? err.message : "Network error");
};

// Log any promise rejection that nothing caught (visibility, not user-facing).
window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled promise rejection:", event.reason);
});

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <SWRConfig value={{ onError: handleSwrError }}>
          <ServiceWorkerRegistrar />
          <RouterProvider router={router} />
        </SWRConfig>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>
);
