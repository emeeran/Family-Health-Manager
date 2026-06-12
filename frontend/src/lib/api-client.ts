import { API_BASE_URL } from "./constants";

export class ApiError extends Error {
  constructor(
    public status: number,
    public data: { status_code?: number; error?: string; message: string; details?: string[] }
  ) {
    super(data.message);
    this.name = "ApiError";
  }
}

interface ApiOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string | undefined>;
  isFormData?: boolean;
  /** Override default request timeout (ms). */
  timeout?: number;
  /** Internal: true when this request is a retry after token refresh. */
  _isRetry?: boolean;
}

const REQUEST_TIMEOUT = 30_000;

/* ------------------------------------------------------------------ */
/*  Automatic token refresh                                            */
/* ------------------------------------------------------------------ */

/**
 * Mutex-protected refresh. Only one refresh call runs at a time;
 * concurrent 401s all await the same in-flight refresh.
 */
let refreshPromise: Promise<boolean> | null = null;

export async function tryRefreshToken(): Promise<boolean> {
  // Reuse in-flight refresh if one is already running
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

function forceLogout(): never {
  fetch(`${API_BASE_URL}/auth/logout`, { method: "POST", credentials: "include" }).catch(() => {});
  window.location.href = "/login";
  throw new ApiError(401, { message: "Session expired" });
}

/* ------------------------------------------------------------------ */
/*  apiRequest                                                         */
/* ------------------------------------------------------------------ */

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, params, isFormData = false, timeout, _isRetry = false } = options;

  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        sp.set(key, value);
      }
    });
  }
  const qs = sp.toString();
  const url = `${API_BASE_URL}${path}${qs ? `?${qs}` : ""}`;

  const headers: Record<string, string> = {};
  if (!isFormData && body) {
    headers["Content-Type"] = "application/json";
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout ?? REQUEST_TIMEOUT);

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: isFormData ? (body as FormData) : body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      credentials: "include",
    });

    // ── 401: try refresh then retry once ──
    if (response.status === 401 && !path.startsWith("/auth/")) {
      if (_isRetry) {
        // Already retried after refresh — session is definitely dead
        forceLogout();
      }
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        return apiRequest<T>(path, { ...options, _isRetry: true });
      }
      forceLogout();
    }

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      let error;
      try {
        const parsed = JSON.parse(text);
        // Normalize FastAPI error format: {"detail": "..."} → {"message": "..."}
        if (parsed.detail && !parsed.message) {
          parsed.message = parsed.detail;
        }
        error = parsed;
      } catch {
        error = {
          status_code: response.status,
          message: response.statusText || `HTTP ${response.status}`,
          detail: text.slice(0, 200),
        };
      }
      console.error(`API ${response.status} on ${path}:`, error);
      throw new ApiError(response.status, error);
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(408, { message: "Request timed out" });
    }
    if (err instanceof TypeError) {
      throw new ApiError(0, { message: "Network error. Check your connection." });
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

/* ------------------------------------------------------------------ */
/*  streamRequest (SSE)                                                */
/* ------------------------------------------------------------------ */

/**
 * Stream SSE events from a POST endpoint.
 * Calls `onEvent` for each parsed JSON event from the server.
 * Returns a promise that resolves when the stream ends.
 * Call the returned cancel function to abort the stream at any time.
 */
export function streamRequest(
  path: string,
  options: {
    body?: unknown;
    onEvent: (event: Record<string, unknown>) => void;
  },
  _isRetry = false
): { promise: Promise<void>; cancel: () => void } {
  const { body, onEvent } = options;
  const url = `${API_BASE_URL}${path}`;

  const headers: Record<string, string> = {};
  if (body) headers["Content-Type"] = "application/json";

  const controller = new AbortController();
  // AI streaming can take minutes — use 5 min timeout
  const STREAM_TIMEOUT = 300_000;
  const timeoutId = setTimeout(() => controller.abort(), STREAM_TIMEOUT);

  const promise = (async () => {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
        credentials: "include",
      });

      // ── 401: try refresh then retry once ──
      if (response.status === 401 && !path.startsWith("/auth/")) {
        if (_isRetry) forceLogout();
        const refreshed = await tryRefreshToken();
        if (refreshed) {
          const retry = streamRequest(path, options, true);
          return retry.promise;
        }
        forceLogout();
      }

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        let error;
        try {
          error = JSON.parse(text);
        } catch {
          error = {
            status_code: response.status,
            message: response.statusText || `HTTP ${response.status}`,
            detail: text.slice(0, 200),
          };
        }
        console.error(`Stream ${response.status} on ${path}:`, error);
        throw new ApiError(response.status, error);
      }

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith("data: ")) {
              try {
                const event = JSON.parse(trimmed.slice(6));
                onEvent(event);
              } catch {
                // Skip malformed JSON lines
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (err instanceof DOMException && err.name === "AbortError") {
        // User-initiated cancel vs timeout
        if (controller.signal.aborted && !timeoutId.refresh) {
          return; // Cancelled by user — resolve silently
        }
        throw new ApiError(408, { message: "Request timed out" });
      }
      if (err instanceof TypeError) {
        throw new ApiError(0, { message: "Network error. Check your connection." });
      }
      throw err;
    } finally {
      clearTimeout(timeoutId);
    }
  })();

  return {
    promise,
    cancel: () => {
      clearTimeout(timeoutId);
      controller.abort();
    },
  };
}
