const API_BASE_URL = import.meta.env.VITE_API_URL || "";

/**
 * Call the backend logout endpoint to clear the httpOnly cookie,
 * then redirect to the login page.
 */
export async function clearToken(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // best-effort — the cookie may still be cleared server-side
  }
  window.location.href = "/login";
}

/**
 * With cookie-based auth we cannot inspect the token from JS.
 * Return true so that route guards render the app; the api-client
 * handles 401 responses by redirecting to /login automatically.
 */
export function isAuthenticated(): boolean {
  return true;
}
