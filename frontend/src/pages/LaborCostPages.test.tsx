import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../features/auth/AuthContext";
import { LaborCostMonthlyPage } from "./LaborCostMonthlyPage";
import { LaborCostSettingsPage } from "./LaborCostSettingsPage";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
const openMock = vi.spyOn(window, "open").mockImplementation(() => null);

const paginated = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const locations = paginated([{ id: "l1", name: "本館", code: "main", is_active: true }]);
const staff = paginated([
  {
    id: "s1",
    username: "staff1",
    display_name: "スタッフA",
    employee_code: "EMP-1",
    email: "",
    employment_status: "active",
    roles: ["staff"],
    permissions: [],
    is_active: true,
  },
]);
const rate = {
  id: "r1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  staff: "s1",
  staff_display_name: "スタッフA",
  employee_code: "EMP-1",
  employment_type: "hourly",
  base_hourly_rate: "1200.00",
  fixed_monthly_amount: null,
  valid_from: "2026-07-01",
  valid_to: null,
  notes: "",
  is_active: true,
  created_at: "",
  updated_at: "",
};
const allowance = {
  id: "a1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  staff: "s1",
  staff_display_name: "スタッフA",
  employee_code: "EMP-1",
  code: "day",
  name: "日額手当",
  allowance_type: "per_worked_day",
  amount: "500.00",
  valid_from: "2026-07-01",
  valid_to: null,
  notes: "",
  is_active: true,
  created_at: "",
  updated_at: "",
};
const estimatePeriod = {
  id: "p1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  year: 2026,
  month: 7,
  attendance_closing_period: "c1",
  attendance_closing_period_name: "7月締め",
  attendance_closing_period_status: "closed",
  name: "2026年7月 概算人件費",
  description: "",
  status: "review",
  content_hash: "",
  validation_fingerprint: "",
  finalized_at: null,
  finalized_by: null,
  finalized_by_display_name: "",
  reopened_at: null,
  reopened_by: null,
  reopened_by_display_name: "",
  record_snapshot_count: 0,
  staff_summary_count: 0,
  allowance_snapshot_count: 0,
  created_at: "",
  updated_at: "",
  is_active: true,
};
const closingPeriod = {
  id: "c1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  year: 2026,
  month: 7,
  name: "7月締め",
  description: "",
  status: "closed",
  content_hash: "closing-hash",
  validation_fingerprint: "closing-fp",
  closed_at: null,
  closed_by: null,
  closed_by_display_name: "",
  reopened_at: null,
  reopened_by: null,
  reopened_by_display_name: "",
  snapshot_count: 1,
  staff_summary_count: 1,
  labor_cost_estimate_period: "p1",
  labor_cost_estimate_status: "review",
  labor_cost_estimate_name: "2026年7月 概算人件費",
  created_at: "",
  updated_at: "",
  is_active: true,
};
const preview = {
  period: "p1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  year: 2026,
  month: 7,
  status: "review",
  attendance_closing_period: "c1",
  attendance_closing_status: "closed",
  source_status: "closed",
  content_hash: "hash",
  validation_fingerprint: "fingerprint",
  summary: {
    date_from: "2026-07-01",
    date_to: "2026-07-31",
    record_snapshot_count: 1,
    staff_summary_count: 1,
    allowance_snapshot_count: 1,
    staff_count: 1,
    warning_count: 1,
    error_count: 0,
    worked_minutes: 420,
    worked_hours_decimal: "7.00",
    base_pay_total: "8400",
    allowance_total: "2200",
    estimated_total: "10600",
  },
  issues: [],
  record_snapshots: [
    {
      attendance_closing_snapshot: "cs1",
      attendance_record: "ar1",
      location: "l1",
      location_name: "本館",
      staff: "s1",
      staff_display_name: "スタッフA",
      employee_code: "EMP-1",
      work_date: "2026-07-01",
      employment_type_snapshot: "hourly",
      base_hourly_rate_snapshot: "1200.00",
      fixed_monthly_amount_snapshot: null,
      worked_minutes: 420,
      worked_hours_decimal: "7.00",
      base_pay: "8400",
      allowance_total: "1200",
      estimated_total: "9600",
      warning_count: 0,
      warnings: [],
      error_count: 0,
      errors: [],
    },
  ],
  staff_summaries: [
    {
      staff: "s1",
      staff_display_name_snapshot: "スタッフA",
      employee_code_snapshot: "EMP-1",
      employment_type_snapshot: "hourly",
      base_hourly_rate_snapshot: "1200.00",
      fixed_monthly_amount_snapshot: null,
      worked_days: 1,
      worked_minutes: 420,
      worked_hours_decimal: "7.00",
      base_pay_total: "8400",
      allowance_total: "2200",
      estimated_total: "10600",
      warning_count: 1,
      error_count: 0,
    },
  ],
  allowance_snapshots: [
    {
      staff: "s1",
      staff_display_name_snapshot: "スタッフA",
      employee_code_snapshot: "EMP-1",
      allowance_assignment: "a1",
      code_snapshot: "manual",
      name_snapshot: "手入力手当",
      allowance_type_snapshot: "manual",
      amount_snapshot: "999.00",
      quantity: "0",
      estimated_amount: "0",
      warning_count: 1,
      warnings: [{ severity: "warning", code: "manual_allowance_not_calculated", message: "manual" }],
    },
  ],
  can_finalize: true,
};

function renderWithAuth(element: ReactNode, roles = ["system_admin"]) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <Routes>
            <Route path="/" element={element} />
            <Route path="/403" element={<div>forbidden</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return roles;
}

function mockApi(roles = ["system_admin"]) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/me/")) {
      return {
        ok: true,
        json: async () => ({
          id: "u1",
          username: "user",
          display_name: "表示ユーザー",
          employee_code: "EMP-1",
          email: "",
          employment_status: "active",
          must_change_password: false,
          roles,
          permissions: [],
        }),
      } as Response;
    }
    if (url.endsWith("/api/v1/auth/csrf/")) return { ok: true, json: async () => ({}) } as Response;
    if (url.includes("/api/v1/locations/")) return { ok: true, json: async () => locations } as Response;
    if (url.includes("/api/v1/staff/?")) return { ok: true, json: async () => staff } as Response;
    if (url.includes("/preview/")) return { ok: true, json: async () => preview } as Response;
    if (url.includes("/finalize/")) {
      return { ok: true, json: async () => ({ ...estimatePeriod, status: "finalized" }) } as Response;
    }
    if (url.includes("/attendance-closing-periods/")) {
      return { ok: true, json: async () => paginated([closingPeriod]) } as Response;
    }
    if (url.includes("/staff-compensation-profiles/") && method === "GET") {
      return { ok: true, json: async () => paginated([rate]) } as Response;
    }
    if (url.includes("/staff-allowance-assignments/") && method === "GET") {
      return { ok: true, json: async () => paginated([allowance]) } as Response;
    }
    if (url.includes("/labor-cost-estimate-periods/") && method === "GET") {
      return { ok: true, json: async () => paginated([estimatePeriod]) } as Response;
    }
    return { ok: true, json: async () => ({ ...rate, id: "created" }) } as Response;
  });
}

describe("LaborCost pages", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    openMock.mockClear();
  });

  afterEach(() => cleanup());

  it("lists, creates, edits, and deactivates staff compensation profiles", async () => {
    mockApi();
    const user = userEvent.setup();
    renderWithAuth(<LaborCostSettingsPage resource="rates" />);

    expect(await screen.findByRole("heading", { name: "勤務単価設定" })).toBeInTheDocument();
    expect(await screen.findByText("1200.00")).toBeInTheDocument();
    await user.selectOptions(screen.getAllByLabelText("拠点")[1], "l1");
    await user.selectOptions(screen.getAllByLabelText("スタッフ")[1], "s1");
    await user.type(screen.getByLabelText("有効開始"), "2026-07-01");
    await user.type(screen.getByLabelText("時給"), "1300");
    await user.click(screen.getByRole("button", { name: "作成" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/staff-compensation-profiles/",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "編集" }));
    expect(screen.getByLabelText("時給")).toHaveValue("1200.00");
    await user.click(screen.getByRole("button", { name: "無効化" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/staff-compensation-profiles/r1/",
        expect.objectContaining({ method: "PATCH" }),
      ),
    );
  });

  it("keeps labor settings hidden from supervisors", async () => {
    mockApi(["supervisor"]);
    renderWithAuth(<LaborCostSettingsPage resource="allowances" />, ["supervisor"]);
    expect(await screen.findByText("forbidden")).toBeInTheDocument();
  });

  it("previews, finalizes, and exports monthly labor cost estimates", async () => {
    mockApi();
    const user = userEvent.setup();
    renderWithAuth(<LaborCostMonthlyPage />);

    expect(await screen.findByRole("heading", { name: "概算人件費" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "2026-07" }));
    await user.click(screen.getByRole("button", { name: "preview" }));
    expect(await screen.findByText("概算合計 10600")).toBeInTheDocument();
    expect(screen.getByText("manual_allowance_not_calculated")).toBeInTheDocument();
    await user.click(screen.getByLabelText("warning確認済み"));
    await user.click(screen.getByRole("button", { name: "finalize" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/labor-cost-estimate-periods/p1/finalize/",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "CSV出力" }));
    expect(openMock).toHaveBeenCalledWith("/api/v1/labor-cost-estimate-periods/p1/export-csv/", "_blank", "noopener");
  });
});
