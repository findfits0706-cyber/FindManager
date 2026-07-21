export const API_ERROR_EVENT = "findmanager:api-error";
export const SESSION_EXPIRED_EVENT = "findmanager:session-expired";

export type ApiErrorDetail = {
  status: number;
  code: string;
  message: string;
  requestId: string | null;
  errors: unknown;
};

export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string | null;
  errors: unknown;

  constructor(detail: ApiErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.status = detail.status;
    this.code = detail.code;
    this.requestId = detail.requestId;
    this.errors = detail.errors;
  }
}

let csrfToken: string | null = null;

function emit(name: string, detail: ApiErrorDetail) {
  window.dispatchEvent(new CustomEvent<ApiErrorDetail>(name, { detail }));
}

async function ensureCsrf() {
  const response = await fetch("/api/v1/auth/csrf/", { credentials: "include" });
  if (!response.ok) throw new Error("CSRF token request failed.");
  const data = (await response.json()) as { csrfToken?: unknown };
  if (typeof data.csrfToken === "string") csrfToken = data.csrfToken;
}

function stringValue(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (Array.isArray(value) && value.length > 0) return String(value[0]);
  return null;
}

function errorMessage(data: unknown): string {
  if (!data || typeof data !== "object") return "リクエストに失敗しました。";
  if ("message" in data) {
    const message = stringValue(data.message);
    if (message) return message;
  }
  if ("detail" in data) {
    const detail = stringValue(data.detail);
    if (detail) return detail;
  }
  for (const value of Object.values(data)) {
    const message = stringValue(value);
    if (message) return message;
  }
  return "リクエストに失敗しました。";
}

async function responseData(response: Response): Promise<unknown> {
  const contentType = response.headers?.get?.("Content-Type") ?? "";
  if (contentType.includes("application/json") || (!contentType && typeof response.json === "function")) {
    try {
      return await response.json();
    } catch {
      // Fall through to text for non-standard responses and test doubles.
    }
  }
  let text = "";
  try {
    text = typeof response.text === "function" ? await response.text() : "";
  } catch {
    return {};
  }
  return text ? { detail: text } : {};
}

function detailFromResponse(response: Response, data: unknown): ApiErrorDetail {
  const body = data && typeof data === "object" ? data : {};
  return {
    status: response.status,
    code: "code" in body && typeof body.code === "string" ? body.code : `http_${response.status}`,
    message: errorMessage(body),
    requestId:
      "request_id" in body && typeof body.request_id === "string"
        ? body.request_id
        : response.headers?.get?.("X-Request-ID") ?? null,
    errors: "errors" in body ? body.errors : body,
  };
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);

  try {
    if (method !== "GET" && method !== "HEAD") {
      await ensureCsrf();
      if (csrfToken) headers.set("X-CSRFToken", csrfToken);
    }
    if (init?.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

    const response = await fetch(path, {
      ...init,
      credentials: "include",
      headers,
    });

    if (response.status === 204) return undefined as T;
    const data = await responseData(response);
    if (!response.ok) {
      const detail = detailFromResponse(response, data);
      const error = new ApiError(detail);
      if (path !== "/api/v1/auth/me/" && (response.status === 401 || detail.code === "not_authenticated")) {
        emit(SESSION_EXPIRED_EVENT, detail);
      } else if (response.status >= 500) {
        emit(API_ERROR_EVENT, detail);
      }
      throw error;
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const detail: ApiErrorDetail = {
      status: 0,
      code: "network_error",
      message: "サーバーと通信できませんでした。接続を確認して再度お試しください。",
      requestId: null,
      errors: null,
    };
    emit(API_ERROR_EVENT, detail);
    throw new ApiError(detail);
  }
}
