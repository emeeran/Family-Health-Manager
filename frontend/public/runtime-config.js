/*
 * Runtime configuration for the Health Manager frontend.
 *
 * This file is served as a static asset (alongside index.html) and can be
 * edited AFTER the build to repoint the app at a different backend — no rebuild
 * required.
 *
 * Set window.__API_BASE__ to a FULL API base URL (including "/api/v1"), e.g.
 *     window.__API_BASE__ = "https://health.example.com/api/v1";
 * Leave it empty ("") to use the default relative path, which works behind the
 * bundled Caddy reverse proxy (recommended for the standard self-hosted setup).
 */
window.__API_BASE__ = "";
