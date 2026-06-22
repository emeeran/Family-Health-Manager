import { useEffect } from "react";
import { toast } from "sonner";

/**
 * Registers the service worker and surfaces app updates.
 *
 * A new deploy downloads in the background; once it's installed and waiting we
 * show a toast with a "Reload" action. The user chooses when to activate it
 * (so we never reload mid-edit) — clicking posts SKIP_WAITING to the SW, which
 * activates it and triggers a controllerchange → reload.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !import.meta.env.PROD) return;

    let refreshing = false;
    // When a new SW takes control (after the user accepts the update), reload
    // once to load the new assets.
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });

    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => {
        reg.addEventListener("updatefound", () => {
          const newWorker = reg.installing;
          if (!newWorker) return;
          newWorker.addEventListener("statechange", () => {
            // A new version is ready and waiting (controller is set only when
            // an older SW already controls the page — i.e. an update, not the
            // first install).
            if (newWorker.state === "installed" && navigator.serviceWorker.controller) {
              toast.info("A new version is available", {
                duration: Infinity,
                action: {
                  label: "Reload",
                  onClick: () => newWorker.postMessage({ type: "SKIP_WAITING" }),
                },
              });
            }
          });
        });
      })
      .catch(() => {
        // SW registration failed — non-critical, app still works online.
      });
  }, []);

  return null;
}
