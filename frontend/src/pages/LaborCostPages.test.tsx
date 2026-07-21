import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../features/auth/AuthContext";
import { LaborCostBudgetPage } from "./LaborCostBudgetPage";
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
const budgetPeriod = {
  id: "b1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  year: 2026,
  month: 7,
  name: "2026年7月 人件費予算",
  description: "",
  budget_amount: "1000000.00",
  warning_threshold_percent: "90.00",
  critical_threshold_percent: "100.00",
  source_monthly_shift_plan: "plan1",
  source_monthly_shift_plan_name: "7月シフト",
  source_publication: "pub1",
  source_publication_version: 1,
  status: "review",
  content_hash: "",
  validation_fingerprint: "",
  approved_at: null,
  approved_by: null,
  approved_by_display_name: "",
  reopened_at: null,
  reopened_by: null,
  reopened_by_display_name: "",
  plan_record_snapshot_count: 0,
  staff_summary_count: 0,
  daily_summary_count: 0,
  allowance_snapshot_count: 0,
  created_at: "",
  updated_at: "",
  is_active: true,
};
const budgetPreview = {
  period: "b1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  year: 2026,
  month: 7,
  status: "review",
  plan_source: "published",
  source_monthly_shift_plan: "plan1",
  source_publication: "pub1",
  actual_source_status: "finalized",
  actual_estimate_period: "p1",
  actual_content_hash: "actual-hash",
  content_hash: "budget-hash",
  validation_fingerprint: "budget-fingerprint",
  approval_issues: [
    { severity: "warning", code: "planned_budget_warning_threshold", message: "予定原価が警戒閾値です。" },
  ],
  comparison_issues: [],
  summary: {
    budget_amount: "1000000.00",
    planned_total: "920000.00",
    actual_estimated_total: "870000.00",
    planned_budget_variance_amount: "-80000.00",
    planned_budget_variance_percent: "-8.00",
    actual_budget_variance_amount: "-130000.00",
    actual_budget_variance_percent: "-13.00",
    actual_plan_variance_amount: "-50000.00",
    actual_plan_variance_percent: "-5.43",
    planned_budget_ratio_percent: "92.00",
    actual_budget_ratio_percent: "87.00",
    planned_budget_status: "warning",
    actual_budget_status: "normal",
    plan_record_count: 1,
    staff_summary_count: 1,
    daily_summary_count: 1,
    allowance_snapshot_count: 1,
    approval_warning_count: 1,
    approval_error_count: 0,
  },
  plan_records: [
    {
      location: "l1",
      staff: "s1",
      staff_display_name: "スタッフA",
      employee_code: "EMP-1",
      work_date: "2026-07-01",
      monthly_shift_plan: "plan1",
      monthly_shift_assignment: "assignment1",
      publication: "pub1",
      publication_assignment: "pa1",
      plan_source_snapshot: "published",
      employment_type_snapshot: "hourly",
      base_hourly_rate_snapshot: "1200.00",
      fixed_monthly_amount_snapshot: null,
      planned_start_offset_minutes: 540,
      planned_end_offset_minutes: 960,
      planned_worked_minutes: 420,
      planned_hours_decimal: "7.00",
      planned_base_pay: "8400.00",
      planned_daily_allowance: "500.00",
      planned_total: "8900.00",
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
      planned_worked_days: 1,
      planned_worked_minutes: 420,
      planned_hours_decimal: "7.00",
      planned_hourly_base_pay: "8400.00",
      planned_fixed_monthly_pay: "0.00",
      planned_allowance_total: "500.00",
      planned_total: "8900.00",
      actual_worked_minutes: 400,
      actual_base_pay_total: "8000.00",
      actual_allowance_total: "500.00",
      actual_estimated_total: "8500.00",
      actual_plan_variance_amount: "-400.00",
      actual_plan_variance_percent: "-4.49",
      warning_count: 0,
      error_count: 0,
    },
  ],
  daily_summaries: [
    {
      work_date: "2026-07-01",
      planned_staff_count: 1,
      planned_worked_minutes: 420,
      planned_total: "8900.00",
      actual_staff_count: 1,
      actual_worked_minutes: 400,
      actual_estimated_total: "8500.00",
      actual_plan_variance_amount: "-400.00",
      actual_plan_variance_percent: "-4.49",
      warning_count: 0,
      error_count: 0,
    },
  ],
  allowance_snapshots: [
    {
      staff: "s1",
      staff_display_name_snapshot: "スタッフA",
      employee_code_snapshot: "EMP-1",
      allowance_assignment: "a1",
      code_snapshot: "day",
      name_snapshot: "日額手当",
      allowance_type_snapshot: "per_worked_day",
      amount_snapshot: "500.00",
      quantity: "1.00",
      planned_amount: "500.00",
      warning_count: 0,
      warnings: [],
    },
  ],
  can_approve: true,
};
const financialPerformance = {
  period: "rp1",
  location: "l1",
  year: 2026,
  month: 7,
  status: "finalized",
  revenue_budget_source_status: "approved",
  labor_cost_budget_source_status: "approved",
  labor_cost_estimate_source_status: "finalized",
  revenue_budget_period: "rb1",
  labor_cost_budget_period: "b1",
  labor_cost_estimate_period: "p1",
  content_hash: "finance-hash",
  validation_fingerprint: "finance-fingerprint",
  summary: {
    revenue_budget_total: "2000000.00",
    revenue_actual_total: "2100000.00",
    revenue_variance_amount: "100000.00",
    revenue_attainment_percent: "105.00",
    labor_budget_amount: "1000000.00",
    planned_labor_cost: "920000.00",
    actual_labor_cost_estimate: "870000.00",
    budget_labor_cost_ratio: "50.00",
    planned_labor_cost_ratio_to_budget_revenue: "46.00",
    planned_labor_cost_ratio_to_actual_revenue: "43.81",
    actual_labor_cost_ratio: "41.43",
    planned_vs_labor_budget_amount: "-80000.00",
    actual_vs_labor_budget_amount: "-130000.00",
    actual_vs_planned_labor_cost_amount: "-50000.00",
    line_count: 1,
    warning_count: 0,
    error_count: 0,
  },
  performance_lines: [],
  warnings: [],
  errors: [],
  issues: [],
  can_finalize: false,
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
    if (url.includes("/financial-performance/")) {
      return { ok: true, json: async () => financialPerformance } as Response;
    }
    if (url.includes("/labor-cost-budget-periods/") && url.includes("/preview/")) {
      return { ok: true, json: async () => budgetPreview } as Response;
    }
    if (url.includes("/labor-cost-budget-periods/") && url.includes("/variance/")) {
      return { ok: true, json: async () => budgetPreview } as Response;
    }
    if (url.includes("/labor-cost-budget-periods/") && url.includes("/approve/")) {
      return { ok: true, json: async () => ({ ...budgetPeriod, status: "approved" }) } as Response;
    }
    if (url.includes("/labor-cost-budget-periods/") && method === "GET") {
      return { ok: true, json: async () => paginated([budgetPeriod]) } as Response;
    }
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
    expect(await screen.findByText(/1,000,000円/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "人件費予算・予実へ進む" })).toHaveAttribute(
      "href",
      "/labor-cost/budget?location=l1&year=2026&month=7&period=b1",
    );
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

  it("manages labor budgets, shows variance labels, requires warning acknowledgement, and exports CSV", async () => {
    mockApi();
    const user = userEvent.setup();
    renderWithAuth(<LaborCostBudgetPage />);

    expect(await screen.findByRole("heading", { name: "人件費予算・予実" })).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "2026-07" }));
    await user.click(screen.getByRole("button", { name: "プレビュー" }));
    expect(await screen.findByText("予定: 警戒")).toBeInTheDocument();
    expect(screen.getByText(/planned_budget_warning_threshold/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "スタッフ別予実" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "日別予実" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "予定原価明細" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "予定手当" })).toBeInTheDocument();
    const approveButton = screen.getByRole("button", { name: "承認" });
    expect(approveButton).toBeDisabled();
    await user.click(screen.getByLabelText("warning確認済み"));
    expect(approveButton).toBeEnabled();
    await user.click(approveButton);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/labor-cost-budget-periods/b1/approve/",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "CSV出力" }));
    expect(openMock).toHaveBeenCalledWith("/api/v1/labor-cost-budget-periods/b1/export-csv/", "_blank", "noopener");
    await user.selectOptions(screen.getByLabelText("拠点"), "l1");
    expect(await screen.findByRole("link", { name: "売上・人件費率へ進む" })).toHaveAttribute(
      "href",
      "/finance/performance?location=l1&year=2026&month=7",
    );
    expect(screen.getByText("予定人件費率: 43.81%")).toBeInTheDocument();
  });

  it("keeps the labor budget screen inaccessible to supervisors", async () => {
    mockApi(["supervisor"]);
    renderWithAuth(<LaborCostBudgetPage />, ["supervisor"]);
    expect(await screen.findByText("forbidden")).toBeInTheDocument();
  });
});
