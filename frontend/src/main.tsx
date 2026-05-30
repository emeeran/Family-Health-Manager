import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { router } from "./router";
import { ErrorBoundary } from "./components/shared/error-boundary";
import { ServiceWorkerRegistrar } from "./components/shared/register-sw";
import "./globals.css";

const root = document.getElementById("root");
if (!root) throw new Error("Root element not found");

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <ServiceWorkerRegistrar />
        <RouterProvider router={router} />
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>
);
