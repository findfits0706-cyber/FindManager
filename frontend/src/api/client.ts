async function ensureCsrf() {
  await fetch("/api/v1/auth/csrf/", { credentials: "include" });
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

  const data = (await response.json()) as T & { detail?: string };
  if (!response.ok) {
    throw new Error(data.detail ?? "Request failed.");
  }
  return data;
}
