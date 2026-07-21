import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "../features/auth/AuthContext";
import { SystemStatusPage } from "./SystemStatusPage";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const statusData = {
  backend_version: "1.0.0-rc1",
  environment: "production",
  api_health: "ok",
  api_readiness: "ready",
  migration_status: "up_to_date",
  database_status: "connected",
  last_audit_event_at: "2026-07-20T10:00:00+09:00",
  active_location_count: 2,
  active_staff_count: 100,
  pending_request_count: 3,
  unclosed_attendance_period_count: 1,
  unfinalized_labor_estimate_period_count: 2,
  unapproved_labor_budget_period_count: 1,
  unfinalized_revenue_actual_period_count: 4,
};

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

function mockApi(roles: string[], fail = false) {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/auth/me/")) {
      return response({
        id: "1",
        username: "admin",
        display_name: "管理者",
        employee_code: "EMP-1",
        email: "",
        employment_status: "active",
        must_change_password: false,
        roles,
        permissions: [],
      });
    }
    if (url.endsWith("/system/status/")) {
      return fail
        ? response({ code: "server_error", message: "failed", request_id: "status-request" }, 500)
        : response(statusData);
    }
    return response({});
  });
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/system/status"]}>
        <AuthProvider>
          <Routes>
            <Route path="/system/status" element={<SystemStatusPage />} />
            <Route path="/403" element={<div>forbidden</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SystemStatusPage", () => {
  beforeEach(() => fetchMock.mockReset());
  afterEach(() => cleanup());

  it("shows safe system summaries with accessible table labels", async () => {
    mockApi(["system_admin"]);
    renderPage();
    expect(await screen.findByRole("heading", { name: "システム状態" })).toBeInTheDocument();
    expect(await screen.findByText("準備完了")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "バージョンと環境" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "運用集計" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "未確定売上実績" })).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("SECRET_KEY");
  });

  it("redirects non-admin users before requesting status data", async () => {
    mockApi(["shift_manager"]);
    renderPage();
    expect(await screen.findByText("forbidden")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/system/status/"))).toBe(false);
  });

  it("shows request ID when status loading fails", async () => {
    mockApi(["system_admin"], true);
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("システム状態を取得できませんでした");
    expect(screen.getByText("Request ID: status-request")).toBeInTheDocument();
  });
});
