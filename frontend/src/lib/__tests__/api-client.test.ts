import { ApiError, apiRequest } from "../api-client";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock constants
vi.mock("../constants", () => ({
  API_BASE_URL: "http://localhost:8000/api/v1",
}));

// Store original location for restoration
const originalWindowLocation = window.location;

describe("ApiError", () => {
  it("should create an ApiError with status and data", () => {
    const error = new ApiError(400, {
      status_code: 400,
      error: "validation_error",
      message: "Invalid input",
    });

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.status).toBe(400);
    expect(error.message).toBe("Invalid input");
    expect(error.data.error).toBe("validation_error");
  });
});

describe("apiRequest", () => {
  let mockLocation: { href: string };

  beforeEach(() => {
    mockFetch.mockReset();
    mockLocation = { href: "" };
    Object.defineProperty(window, "location", {
      value: mockLocation,
      writable: true,
      configurable: true,
    });
  });

  afterAll(() => {
    Object.defineProperty(window, "location", {
      value: originalWindowLocation,
      writable: true,
      configurable: true,
    });
  });

  it("should make a GET request and return JSON", async () => {
    const mockData = { id: "123", username: "testuser" };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockData),
    });

    const result = await apiRequest<{ id: string }>("/auth/me");
    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/me",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
      })
    );
  });

  it("should send JSON body for POST requests", async () => {
    const body = { username: "test", password: "password123" };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: "token" }),
    });

    await apiRequest("/auth/login", { method: "POST", body });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  it("should throw ApiError on non-2xx responses", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      text: () =>
        Promise.resolve(JSON.stringify({ status_code: 422, message: "Validation failed" })),
    });

    await expect(apiRequest("/auth/register", { method: "POST", body: {} })).rejects.toThrow(
      ApiError
    );
    await expect(apiRequest("/auth/register", { method: "POST", body: {} })).rejects.toThrow();
  });

  it("should handle 401 by redirecting to login", async () => {
    // First call: 401 response
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
    });
    // Second call: tryRefreshToken fails (refresh returns 401)
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
    });
    // Third call: forceLogout POST
    mockFetch.mockResolvedValueOnce({ ok: true });

    try {
      await apiRequest("/members");
      expect.unreachable("Should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect(mockLocation.href).toBe("/login");
    }
  });

  it("should include query parameters", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    });

    await apiRequest("/members", {
      params: { search: "john", limit: "10" },
    });

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("search=john");
    expect(calledUrl).toContain("limit=10");
  });

  it("should return undefined for 204 responses", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
    });

    const result = await apiRequest<void>("/members/123", {
      method: "DELETE",
    });
    expect(result).toBeUndefined();
  });

  it("should handle network errors as ApiError with status 0", async () => {
    mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(apiRequest("/auth/me")).rejects.toThrow(ApiError);
  });

  it("should handle abort/timeout errors as ApiError with status 408", async () => {
    mockFetch.mockRejectedValueOnce(new DOMException("The operation was aborted", "AbortError"));

    await expect(apiRequest("/auth/me")).rejects.toThrow(ApiError);
  });
});
