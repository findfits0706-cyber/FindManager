async function ensureCsrf() {
  await fetch("/api/v1/auth/csrf/", { credentials: "include" });
}

function errorMessage(data: unknown): string {
  if (!data || typeof data !== "object") return "Request failed.";
  if ("detail" in data && typeof data.detail === "string") return data.detail;
  for (const value of Object.values(data)) {
    if (typeof value === "string") return value;
    if (Array.isArray(value) && value.length > 0) return String(value[0]);
  }
  return "Request failed.";
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? "GET";
  if (method !== "GET" && method !== "HEAD") {
    await ensureCsrf();
  }

  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");

  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const data = (await response.json()) as T;
  if (!response.ok) {
    throw new Error(errorMessage(data));
  }
  return data;
}
