import { API_ERROR_EVENT, ApiError, SESSION_EXPIRED_EVENT, api } from "./client";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function response(body: unknown, status = 200, requestId?: string) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "Content-Type": "application/json", ...(requestId ? { "X-Request-ID": requestId } : {}) }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("api client", () => {
  beforeEach(() => fetchMock.mockReset());

  it("sends the CSRF token on unsafe requests", async () => {
    fetchMock.mockResolvedValueOnce(response({ csrfToken: "csrf-value" })).mockResolvedValueOnce(response({ ok: true }));
    await api("/api/v1/resource/", { method: "POST", body: JSON.stringify({ name: "test" }) });
    const request = fetchMock.mock.calls[1][1] as RequestInit;
    expect(new Headers(request.headers).get("X-CSRFToken")).toBe("csrf-value");
    expect(request.credentials).toBe("include");
  });

  it("raises ApiError and emits request ID for server errors", async () => {
    const listener = vi.fn();
    window.addEventListener(API_ERROR_EVENT, listener);
    fetchMock.mockResolvedValueOnce(
      response({ code: "server_error", message: "失敗しました。", errors: {}, request_id: "request-500" }, 500),
    );
    await expect(api("/api/v1/resource/")).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      code: "server_error",
      requestId: "request-500",
    });
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(API_ERROR_EVENT, listener);
  });

  it("emits a session-expired event for authentication failures", async () => {
    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);
    fetchMock.mockResolvedValueOnce(
      response({ code: "not_authenticated", message: "認証が必要です。", request_id: "expired-1" }, 403),
    );
    await expect(api("/api/v1/attendance-records/")).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  });

  it("normalizes network errors without exposing low-level details", async () => {
    fetchMock.mockRejectedValueOnce(new Error("socket secret"));
    await expect(api("/api/v1/health/")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("keeps non-JSON HTTP errors distinct from network failures", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("Service unavailable", {
        status: 503,
        headers: { "Content-Type": "text/plain", "X-Request-ID": "proxy-503" },
      }),
    );
    await expect(api("/api/v1/readiness/")).rejects.toMatchObject({
      status: 503,
      code: "http_503",
      requestId: "proxy-503",
    });
  });
});
