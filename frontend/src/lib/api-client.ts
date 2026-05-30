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
}

const REQUEST_TIMEOUT = 30_000;

function handleUnauthorized(): never {
  fetch(`${API_BASE_URL}/auth/logout`, { method: "POST", credentials: "include" }).catch(() => {});
  window.location.href = "/login";
  throw new ApiError(401, { message: "Session expired" });
}

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, params, isFormData = false } = options;

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
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: isFormData ? (body as FormData) : body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      credentials: "include",
    });

    if (response.status === 401 && !path.startsWith("/auth/login")) handleUnauthorized();

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

/**
 * Stream SSE events from a POST endpoint.
 * Calls `onEvent` for each parsed JSON event from the server.
 * Returns a promise that resolves when the stream ends.
 */
export async function streamRequest(
  path: string,
  options: {
    body?: unknown;
    onEvent: (event: Record<string, unknown>) => void;
  }
): Promise<void> {
  const { body, onEvent } = options;
  const url = `${API_BASE_URL}${path}`;

  const headers: Record<string, string> = {};
  if (body) headers["Content-Type"] = "application/json";

  const controller = new AbortController();
  // AI streaming can take minutes — use 5 min timeout
  const STREAM_TIMEOUT = 300_000;
  const timeoutId = setTimeout(() => controller.abort(), STREAM_TIMEOUT);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      credentials: "include",
    });

    if (response.status === 401 && !path.startsWith("/auth/login")) handleUnauthorized();

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
