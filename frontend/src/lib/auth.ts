const API_BASE_URL = import.meta.env.VITE_API_URL || "";

/**
 * Decode a JWT payload without validating the signature.
 * Returns null if the token is malformed or not provided.
 */
function decodeJwtPayload(token: string | null): Record<string, unknown> | null {
  if (!token) return null;
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    return JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}

/**
 * Cookie-based auth: the JWT is stored in an httpOnly cookie set by the backend.
 * There is no client-accessible token, so this always returns null.
 * Kept for backward compatibility with SWR fetchers that accept a token parameter.
 */
export function getToken(): string | null {
  return null;
}

/**
 * No-op. With httpOnly cookie auth the backend sets the cookie on login.
 * Kept for backward compatibility with login/register forms.
 */
export function setToken(_token: string): void {
  // intentionally empty — cookies are managed by the backend
}

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

/**
 * Decode a JWT token string. Accepts null/undefined gracefully.
 * Useful if any code still needs to inspect token claims.
 */
export { decodeJwtPayload as decodeToken };
