import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../features/auth/AuthContext";
import { FinancePerformancePage } from "./FinancePerformancePage";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
const openMock = vi.spyOn(window, "open").mockImplementation(() => null);

const paginated = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });
const location = { id: "l1", code: "main", name: "本館", short_name: "本館", is_active: true };
const category = {
  id: "c1",
  location: "l1",
  location_name: "本館",
  code: "membership",
  name: "会費",
  short_name: "会費",
  description: "",
  display_order: 10,
  is_active: true,
  created_at: "",
  updated_at: "",
};
const budgetPeriod = {
  id: "b1",
  location: "l1",
  location_name: "本館",
  year: 2026,
  month: 7,
  name: "7月売上予算",
  description: "",
  status: "review",
  content_hash: "",
  validation_fingerprint: "",
  approved_at: null,
  approved_by: null,
  reopened_at: null,
  reopened_by: null,
  line_count: 1,
  is_active: true,
};
const actualPeriod = {
  id: "a1",
  location: "l1",
  location_name: "本館",
  year: 2026,
  month: 7,
  revenue_budget_period: "b1",
  labor_cost_budget_period: "lb1",
  labor_cost_estimate_period: "le1",
  name: "7月売上実績",
  description: "",
  status: "review",
  content_hash: "",
  validation_fingerprint: "",
  finalized_at: null,
  finalized_by: null,
  reopened_at: null,
  reopened_by: null,
  line_count: 1,
  is_active: true,
};
const budgetLine = {
  id: "bl1",
  budget_period: "b1",
  category: "c1",
  category_code: "membership",
  category_name: "会費",
  category_code_snapshot: "membership",
  category_name_snapshot: "会費",
  budget_amount: "1000000.00",
  notes: "",
  display_order: 10,
  is_active: true,
};
const actualLine = {
  id: "al1",
  actual_period: "a1",
  category: "c1",
  category_code: "membership",
  category_name: "会費",
  category_code_snapshot: "membership",
  category_name_snapshot: "会費",
  actual_amount: "1100000.00",
  source: "manual",
  notes: "",
  display_order: 10,
  is_active: true,
};
const issue = { severity: "warning", code: "revenue_budget_below_actual", message: "実績が予算を上回っています。" };
const performance = {
  period: "a1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  year: 2026,
  month: 7,
  status: "review",
  revenue_budget_source_status: "approved",
  labor_cost_budget_source_status: "approved",
  labor_cost_estimate_source_status: "finalized",
  revenue_budget_period: "b1",
  labor_cost_budget_period: "lb1",
  labor_cost_estimate_period: "le1",
  budget_content_hash: "budget-hash",
  labor_budget_content_hash: "labor-budget-hash",
  labor_estimate_content_hash: "estimate-hash",
  content_hash: "performance-hash",
  validation_fingerprint: "performance-fingerprint",
  summary: {
    revenue_budget_total: "1000000.00",
    revenue_actual_total: "1100000.00",
    revenue_variance_amount: "100000.00",
    revenue_attainment_percent: "110.00",
    labor_budget_amount: "300000.00",
    planned_labor_cost: "250000.00",
    actual_labor_cost_estimate: "280000.00",
    budget_labor_cost_ratio: "30.00",
    planned_labor_cost_ratio_to_budget_revenue: "25.00",
    planned_labor_cost_ratio_to_actual_revenue: "22.73",
    actual_labor_cost_ratio: "25.45",
    planned_vs_labor_budget_amount: "-50000.00",
    actual_vs_labor_budget_amount: "-20000.00",
    actual_vs_planned_labor_cost_amount: "30000.00",
    line_count: 1,
    warning_count: 1,
    error_count: 0,
  },
  lines: [actualLine],
  performance_lines: [
    {
      category: "c1",
      category_code_snapshot: "membership",
      category_name_snapshot: "会費",
      budget_amount: "1000000.00",
      actual_amount: "1100000.00",
      variance_amount: "100000.00",
      attainment_percent: "110.00",
      warning_count: 0,
      warnings: [],
      error_count: 0,
      errors: [],
      display_order: 10,
    },
  ],
  warnings: [issue],
  errors: [],
  issues: [issue],
  can_finalize: true,
};
const budgetPreview = {
  period: "b1",
  location: "l1",
  location_name: "本館",
  location_code: "main",
  year: 2026,
  month: 7,
  status: "review",
  content_hash: "budget-hash",
  validation_fingerprint: "budget-fingerprint",
  lines: [budgetLine],
  warnings: [{ severity: "warning", code: "revenue_budget_zero", message: "確認してください。" }],
  errors: [],
  issues: [],
  summary: { budget_total: "1000000.00", line_count: 1, warning_count: 1, error_count: 0 },
  can_approve: true,
};

function mockApi(roles = ["system_admin"], options?: { failCategories?: boolean; empty?: boolean }) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/me/")) {
      return {
        ok: true,
        json: async () => ({
          id: "u1",
          username: "manager",
          display_name: "管理者",
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
    if (url.includes("/locations/")) return { ok: true, json: async () => paginated([location]) } as Response;
    if (url.includes("/revenue-categories/") && method === "GET") {
      if (options?.failCategories) return { ok: false, status: 500, json: async () => ({ detail: "取得失敗" }) } as Response;
      return { ok: true, json: async () => paginated(options?.empty ? [] : [category]) } as Response;
    }
    if (url.includes("/revenue-budget-periods/b1/lines/")) return { ok: true, json: async () => [budgetLine] } as Response;
    if (url.includes("/revenue-budget-periods/b1/preview/")) return { ok: true, json: async () => budgetPreview } as Response;
    if (url.includes("/revenue-budget-periods/b1/approve/")) return { ok: true, json: async () => ({ ...budgetPeriod, status: "approved" }) } as Response;
    if (url.includes("/revenue-budget-periods/b1/reopen/")) return { ok: true, json: async () => ({ ...budgetPeriod, status: "reopened" }) } as Response;
    if (url.includes("/revenue-budget-periods/b1/archive/")) return { ok: true, json: async () => ({ ...budgetPeriod, status: "archived", is_active: false }) } as Response;
    if (url.includes("/revenue-budget-periods/") && method === "GET") return { ok: true, json: async () => paginated(options?.empty ? [] : [budgetPeriod]) } as Response;
    if (url.includes("/revenue-actual-periods/a1/lines/")) return { ok: true, json: async () => [actualLine] } as Response;
    if (url.includes("/revenue-actual-periods/a1/preview/")) return { ok: true, json: async () => performance } as Response;
    if (url.includes("/revenue-actual-periods/a1/finalize/")) return { ok: true, json: async () => ({ ...actualPeriod, status: "finalized" }) } as Response;
    if (url.includes("/revenue-actual-periods/a1/reopen/")) return { ok: true, json: async () => ({ ...actualPeriod, status: "reopened" }) } as Response;
    if (url.includes("/revenue-actual-periods/a1/archive/")) return { ok: true, json: async () => ({ ...actualPeriod, status: "archived", is_active: false }) } as Response;
    if (url.includes("/revenue-actual-periods/") && method === "GET") return { ok: true, json: async () => paginated(options?.empty ? [] : [actualPeriod]) } as Response;
    if (url.includes("/financial-performance/")) return { ok: true, json: async () => performance } as Response;
    if (url.includes("/revenue-categories/") && method === "PATCH") return { ok: true, json: async () => ({ ...category, name: "更新会費", is_active: false }) } as Response;
    if (url.includes("/revenue-categories/") && method === "POST") return { ok: true, json: async () => ({ ...category, id: "created-category" }) } as Response;
    if (url.includes("/revenue-budget-lines/") || url.includes("/revenue-actual-lines/")) return { ok: true, json: async () => ({}) } as Response;
    if (url.includes("/revenue-budget-periods/") && method === "POST") return { ok: true, json: async () => budgetPeriod } as Response;
    if (url.includes("/revenue-actual-periods/") && method === "POST") return { ok: true, json: async () => actualPeriod } as Response;
    return { ok: true, json: async () => ({}) } as Response;
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/finance/performance?year=2026&month=7"]}>
        <AuthProvider>
          <Routes>
            <Route path="/finance/performance" element={<FinancePerformancePage />} />
            <Route path="/403" element={<div>forbidden</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function selectMainLocation(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("option", { name: "本館" });
  await user.selectOptions(screen.getByLabelText("拠点"), "l1");
}

describe("FinancePerformancePage", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    openMock.mockClear();
  });

  afterEach(() => cleanup());

  it("shows the monthly performance summary, category variance, yen, percent, and source states", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByRole("heading", { name: "売上・人件費率" })).toBeInTheDocument();
    await selectMainLocation(user);
    expect((await screen.findAllByText("￥1,100,000")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("￥100,000").length).toBeGreaterThan(0);
    expect(screen.getAllByText("110.00%").length).toBeGreaterThan(0);
    expect(screen.getByText("25.45%")).toBeInTheDocument();
    expect(screen.getByText("売上予算: 承認済み")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "売上区分" })).toBeInTheDocument();
    expect(screen.getByText(/revenue_budget_below_actual/)).toBeInTheDocument();
  });

  it("creates, edits, and deactivates revenue categories", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await selectMainLocation(user);
    await user.click(screen.getByRole("tab", { name: "売上区分" }));
    await user.type(screen.getByLabelText("コード"), "school");
    await user.type(screen.getByLabelText("名称"), "スクール");
    await user.type(screen.getByLabelText("短縮名"), "スクール");
    await user.click(screen.getByRole("button", { name: "作成" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/revenue-categories/", expect.objectContaining({ method: "POST" })));
    await user.click(screen.getByRole("button", { name: "membership" }));
    await user.clear(screen.getByLabelText("名称"));
    await user.type(screen.getByLabelText("名称"), "更新会費");
    await user.click(screen.getByRole("button", { name: "編集" }));
    await user.click(screen.getByRole("button", { name: "無効化" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/revenue-categories/c1/", expect.objectContaining({ method: "PATCH" })));
  });

  it("edits budget lines, previews, requires warning acknowledgement, approves, and exports", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await selectMainLocation(user);
    await user.click(screen.getByRole("tab", { name: "売上予算" }));
    await user.click(await screen.findByRole("button", { name: "2026-07" }));
    expect(await screen.findByLabelText("会費の予算額")).toHaveValue(1000000);
    await user.click(screen.getByRole("button", { name: "明細保存" }));
    await user.click(screen.getByRole("button", { name: "プレビュー" }));
    expect(await screen.findByText(/revenue_budget_zero/)).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: "承認" });
    expect(approve).toBeDisabled();
    await user.click(screen.getByLabelText("warning確認済み"));
    expect(approve).toBeEnabled();
    await user.click(approve);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/revenue-budget-periods/b1/approve/", expect.objectContaining({ method: "POST" })));
    await user.click(screen.getByRole("button", { name: "CSV出力" }));
    expect(openMock).toHaveBeenCalledWith("/api/v1/revenue-budget-periods/b1/export-csv/", "_blank", "noopener");
  });

  it("edits actual lines, previews ratios, finalizes, and exports", async () => {
    mockApi();
    const user = userEvent.setup();
    renderPage();
    await selectMainLocation(user);
    await user.click(screen.getByRole("tab", { name: "売上実績" }));
    await user.click(await screen.findByRole("button", { name: "2026-07" }));
    expect(await screen.findByLabelText("会費の実績額")).toHaveValue(1100000);
    await user.click(screen.getByRole("button", { name: "明細保存" }));
    await user.click(screen.getByRole("button", { name: "プレビュー" }));
    expect(await screen.findByText("22.73%")).toBeInTheDocument();
    await user.click(screen.getByLabelText("warning確認済み"));
    await user.click(screen.getByRole("button", { name: "確定" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/revenue-actual-periods/a1/finalize/", expect.objectContaining({ method: "POST" })));
    await user.click(screen.getByRole("button", { name: "CSV出力" }));
    expect(openMock).toHaveBeenCalledWith("/api/v1/revenue-actual-periods/a1/export-csv/", "_blank", "noopener");
  });

  it("shows empty and API error states and redirects unauthorized roles", async () => {
    mockApi(["system_admin"], { empty: true, failCategories: true });
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("財務管理データの取得に失敗しました。")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "売上予算" }));
    expect(screen.getByText("対象月の売上予算はありません。")).toBeInTheDocument();
    cleanup();
    fetchMock.mockReset();
    mockApi(["supervisor"]);
    renderPage();
    expect(await screen.findByText("forbidden")).toBeInTheDocument();
  });
});
