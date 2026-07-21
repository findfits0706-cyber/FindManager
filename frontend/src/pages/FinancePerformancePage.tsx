import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type {
  Location,
  Paginated,
  RevenueActualLine,
  RevenueActualPeriod,
  RevenueBudgetLine,
  RevenueBudgetPeriod,
  RevenueBudgetPreview,
  RevenueCategory,
  RevenueIssue,
  RevenuePerformance,
} from "../lib/types";

type FinanceTab = "summary" | "categories" | "budget" | "actual";

const today = new Date();
const statusLabels: Record<string, string> = {
  draft: "下書き",
  review: "確認中",
  approved: "承認済み",
  finalized: "確定済み",
  reopened: "再オープン",
  archived: "アーカイブ",
  live: "暫定値",
  unavailable: "利用不可",
};

function statusLabel(value: string) {
  return statusLabels[value] ?? value;
}

function yen(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "算出不可";
  return new Intl.NumberFormat("ja-JP", {
    style: "currency",
    currency: "JPY",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function percent(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "算出不可";
  return `${Number(value).toLocaleString("ja-JP", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

function Issues({ items, emptyText }: { items: RevenueIssue[]; emptyText: string }) {
  if (!items.length) return <p className="subtle-text">{emptyText}</p>;
  return (
    <ul className="issue-list">
      {items.map((item, index) => (
        <li key={`${item.code}-${item.category ?? "all"}-${index}`}>
          <strong>{item.severity}: {item.code}</strong>
          <span>{item.message}{item.category ? ` / ${item.category}` : ""}</span>
        </li>
      ))}
    </ul>
  );
}

export function FinancePerformancePage() {
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const [tab, setTab] = useState<FinanceTab>("summary");
  const [year, setYear] = useState(Number(searchParams.get("year")) || today.getFullYear());
  const [month, setMonth] = useState(Number(searchParams.get("month")) || today.getMonth() + 1);
  const [location, setLocation] = useState(searchParams.get("location") ?? "");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [selectedCategory, setSelectedCategory] = useState<RevenueCategory | null>(null);
  const [categoryCode, setCategoryCode] = useState("");
  const [categoryName, setCategoryName] = useState("");
  const [categoryShortName, setCategoryShortName] = useState("");
  const [categoryDescription, setCategoryDescription] = useState("");
  const [categoryOrder, setCategoryOrder] = useState(0);

  const [selectedBudget, setSelectedBudget] = useState<RevenueBudgetPeriod | null>(null);
  const [budgetName, setBudgetName] = useState("");
  const [budgetDescription, setBudgetDescription] = useState("");
  const [budgetLines, setBudgetLines] = useState<RevenueBudgetLine[]>([]);
  const [budgetAmounts, setBudgetAmounts] = useState<Record<string, string>>({});
  const [budgetPreview, setBudgetPreview] = useState<RevenueBudgetPreview | null>(null);
  const [budgetAck, setBudgetAck] = useState(false);

  const [selectedActual, setSelectedActual] = useState<RevenueActualPeriod | null>(null);
  const [actualName, setActualName] = useState("");
  const [actualDescription, setActualDescription] = useState("");
  const [actualLines, setActualLines] = useState<RevenueActualLine[]>([]);
  const [actualAmounts, setActualAmounts] = useState<Record<string, string>>({});
  const [actualPreview, setActualPreview] = useState<RevenuePerformance | null>(null);
  const [actualAck, setActualAck] = useState(false);

  const monthQuery = useMemo(() => {
    const params = new URLSearchParams({ year: String(year), month: String(month), is_active: "true", page_size: "100" });
    if (location) params.set("location", location);
    return params.toString();
  }, [location, month, year]);

  const categoriesQueryString = useMemo(() => {
    const params = new URLSearchParams({ page_size: "100" });
    if (location) params.set("location", location);
    return params.toString();
  }, [location]);

  const locationsQuery = useQuery({
    queryKey: ["finance-locations"],
    queryFn: () => api<Paginated<Location>>( "/api/v1/locations/?page_size=100"),
    enabled: canManage,
  });
  const categoriesQuery = useQuery({
    queryKey: ["revenue-categories", categoriesQueryString],
    queryFn: () => api<Paginated<RevenueCategory>>(`/api/v1/revenue-categories/?${categoriesQueryString}`),
    enabled: canManage,
  });
  const budgetsQuery = useQuery({
    queryKey: ["revenue-budget-periods", monthQuery],
    queryFn: () => api<Paginated<RevenueBudgetPeriod>>(`/api/v1/revenue-budget-periods/?${monthQuery}`),
    enabled: canManage,
  });
  const actualsQuery = useQuery({
    queryKey: ["revenue-actual-periods", monthQuery],
    queryFn: () => api<Paginated<RevenueActualPeriod>>(`/api/v1/revenue-actual-periods/?${monthQuery}`),
    enabled: canManage,
  });
  const performanceQuery = useQuery({
    queryKey: ["financial-performance", location, year, month],
    queryFn: () =>
      api<RevenuePerformance>(`/api/v1/financial-performance/?location=${location}&year=${year}&month=${month}`),
    enabled: canManage && Boolean(location),
  });

  if (!loading && !canManage) return <Navigate to="/403" replace />;

  const categories = categoriesQuery.data?.results ?? [];
  const activeCategories = categories.filter((item) => item.is_active);
  const budgets = budgetsQuery.data?.results ?? [];
  const actuals = actualsQuery.data?.results ?? [];
  const performance = actualPreview ?? performanceQuery.data ?? null;

  const clearFeedback = () => {
    setError("");
    setMessage("");
  };

  const refreshFinance = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["revenue-categories"] }),
      queryClient.invalidateQueries({ queryKey: ["revenue-budget-periods"] }),
      queryClient.invalidateQueries({ queryKey: ["revenue-actual-periods"] }),
      queryClient.invalidateQueries({ queryKey: ["financial-performance"] }),
    ]);
  };

  const run = async (operation: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    clearFeedback();
    try {
      await operation();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "操作に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const chooseCategory = (category: RevenueCategory) => {
    setSelectedCategory(category);
    setCategoryCode(category.code);
    setCategoryName(category.name);
    setCategoryShortName(category.short_name);
    setCategoryDescription(category.description);
    setCategoryOrder(category.display_order);
    clearFeedback();
  };

  const resetCategory = () => {
    setSelectedCategory(null);
    setCategoryCode("");
    setCategoryName("");
    setCategoryShortName("");
    setCategoryDescription("");
    setCategoryOrder(0);
  };

  const saveCategory = () => run(async () => {
    if (!location) throw new Error("拠点を選択してください。");
    const payload = {
      location,
      code: categoryCode,
      name: categoryName,
      short_name: categoryShortName,
      description: categoryDescription,
      display_order: categoryOrder,
    };
    const saved = selectedCategory
      ? await api<RevenueCategory>(`/api/v1/revenue-categories/${selectedCategory.id}/`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        })
      : await api<RevenueCategory>("/api/v1/revenue-categories/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
    chooseCategory(saved);
    setMessage(selectedCategory ? "売上区分を更新しました。" : "売上区分を作成しました。");
    await refreshFinance();
  });

  const deactivateCategory = () => run(async () => {
    if (!selectedCategory) return;
    const updated = await api<RevenueCategory>(`/api/v1/revenue-categories/${selectedCategory.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: false }),
    });
    chooseCategory(updated);
    setMessage("売上区分を無効化しました。");
    await refreshFinance();
  });

  const chooseBudget = (period: RevenueBudgetPeriod) => run(async () => {
    setSelectedBudget(period);
    setBudgetName(period.name);
    setBudgetDescription(period.description);
    setBudgetPreview(null);
    setBudgetAck(false);
    const lines = await api<RevenueBudgetLine[]>(`/api/v1/revenue-budget-periods/${period.id}/lines/`);
    setBudgetLines(lines);
    setBudgetAmounts(Object.fromEntries(lines.filter((line) => line.is_active).map((line) => [line.category, line.budget_amount])));
  });

  const resetBudget = () => {
    setSelectedBudget(null);
    setBudgetName("");
    setBudgetDescription("");
    setBudgetLines([]);
    setBudgetAmounts({});
    setBudgetPreview(null);
    setBudgetAck(false);
  };

  const saveBudgetPeriod = () => run(async () => {
    if (!location) throw new Error("拠点を選択してください。");
    const payload = { location, year, month, name: budgetName, description: budgetDescription };
    const saved = selectedBudget
      ? await api<RevenueBudgetPeriod>(`/api/v1/revenue-budget-periods/${selectedBudget.id}/`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        })
      : await api<RevenueBudgetPeriod>("/api/v1/revenue-budget-periods/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
    setSelectedBudget(saved);
    setBudgetName(saved.name);
    setMessage(selectedBudget ? "売上予算periodを更新しました。" : "売上予算periodを作成しました。");
    await refreshFinance();
  });

  const saveBudgetLines = () => run(async () => {
    if (!selectedBudget) throw new Error("売上予算periodを選択してください。");
    const existing = new Map(budgetLines.map((line) => [line.category, line]));
    await Promise.all(activeCategories.map(async (category, index) => {
      const amount = budgetAmounts[category.id];
      if (amount === undefined || amount === "") return;
      const line = existing.get(category.id);
      if (line) {
        await api(`/api/v1/revenue-budget-lines/${line.id}/`, {
          method: "PATCH",
          body: JSON.stringify({ budget_amount: amount, display_order: index * 10, is_active: true }),
        });
      } else {
        await api("/api/v1/revenue-budget-lines/", {
          method: "POST",
          body: JSON.stringify({
            budget_period: selectedBudget.id,
            category: category.id,
            budget_amount: amount,
            display_order: index * 10,
          }),
        });
      }
    }));
    const lines = await api<RevenueBudgetLine[]>(`/api/v1/revenue-budget-periods/${selectedBudget.id}/lines/`);
    setBudgetLines(lines);
    setBudgetPreview(null);
    setMessage("売上予算明細を保存しました。");
    await refreshFinance();
  });

  const previewBudget = () => run(async () => {
    if (!selectedBudget) return;
    const preview = await api<RevenueBudgetPreview>(
      `/api/v1/revenue-budget-periods/${selectedBudget.id}/preview/`,
      { method: "POST", body: JSON.stringify({}) },
    );
    setBudgetPreview(preview);
    setMessage("売上予算previewを更新しました。");
    await refreshFinance();
  });

  const approveBudget = () => run(async () => {
    if (!selectedBudget || !budgetPreview) return;
    const updated = await api<RevenueBudgetPeriod>(
      `/api/v1/revenue-budget-periods/${selectedBudget.id}/approve/`,
      {
        method: "POST",
        body: JSON.stringify({
          validation_fingerprint: budgetPreview.validation_fingerprint,
          acknowledge_warnings: budgetAck,
        }),
      },
    );
    setSelectedBudget(updated);
    setMessage("売上予算を承認しました。");
    await refreshFinance();
  });

  const budgetAction = (action: "reopen" | "archive") => run(async () => {
    if (!selectedBudget) return;
    const updated = await api<RevenueBudgetPeriod>(
      `/api/v1/revenue-budget-periods/${selectedBudget.id}/${action}/`,
      { method: "POST", body: JSON.stringify({}) },
    );
    setSelectedBudget(updated);
    setBudgetPreview(null);
    setMessage(action === "reopen" ? "売上予算を再オープンしました。" : "売上予算をアーカイブしました。");
    await refreshFinance();
  });

  const chooseActual = (period: RevenueActualPeriod) => run(async () => {
    setSelectedActual(period);
    setActualName(period.name);
    setActualDescription(period.description);
    setActualPreview(null);
    setActualAck(false);
    const lines = await api<RevenueActualLine[]>(`/api/v1/revenue-actual-periods/${period.id}/lines/`);
    setActualLines(lines);
    setActualAmounts(Object.fromEntries(lines.filter((line) => line.is_active).map((line) => [line.category, line.actual_amount])));
  });

  const resetActual = () => {
    setSelectedActual(null);
    setActualName("");
    setActualDescription("");
    setActualLines([]);
    setActualAmounts({});
    setActualPreview(null);
    setActualAck(false);
  };

  const saveActualPeriod = () => run(async () => {
    if (!location) throw new Error("拠点を選択してください。");
    const payload = { location, year, month, name: actualName, description: actualDescription };
    const saved = selectedActual
      ? await api<RevenueActualPeriod>(`/api/v1/revenue-actual-periods/${selectedActual.id}/`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        })
      : await api<RevenueActualPeriod>("/api/v1/revenue-actual-periods/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
    setSelectedActual(saved);
    setActualName(saved.name);
    setMessage(selectedActual ? "売上実績periodを更新しました。" : "売上実績periodを作成しました。");
    await refreshFinance();
  });

  const saveActualLines = () => run(async () => {
    if (!selectedActual) throw new Error("売上実績periodを選択してください。");
    const existing = new Map(actualLines.map((line) => [line.category, line]));
    await Promise.all(activeCategories.map(async (category, index) => {
      const amount = actualAmounts[category.id];
      if (amount === undefined || amount === "") return;
      const line = existing.get(category.id);
      if (line) {
        await api(`/api/v1/revenue-actual-lines/${line.id}/`, {
          method: "PATCH",
          body: JSON.stringify({ actual_amount: amount, display_order: index * 10, is_active: true }),
        });
      } else {
        await api("/api/v1/revenue-actual-lines/", {
          method: "POST",
          body: JSON.stringify({
            actual_period: selectedActual.id,
            category: category.id,
            actual_amount: amount,
            source: "manual",
            display_order: index * 10,
          }),
        });
      }
    }));
    const lines = await api<RevenueActualLine[]>(`/api/v1/revenue-actual-periods/${selectedActual.id}/lines/`);
    setActualLines(lines);
    setActualPreview(null);
    setMessage("売上実績明細を保存しました。");
    await refreshFinance();
  });

  const previewActual = () => run(async () => {
    if (!selectedActual) return;
    const finalized = selectedActual.status === "finalized";
    const preview = await api<RevenuePerformance>(
      `/api/v1/revenue-actual-periods/${selectedActual.id}/${finalized ? "performance" : "preview"}/`,
      finalized ? undefined : { method: "POST", body: JSON.stringify({}) },
    );
    setActualPreview(preview);
    setMessage(finalized ? "確定snapshotを表示しました。" : "売上実績previewを更新しました。");
    await refreshFinance();
  });

  const finalizeActual = () => run(async () => {
    if (!selectedActual || !actualPreview) return;
    const updated = await api<RevenueActualPeriod>(
      `/api/v1/revenue-actual-periods/${selectedActual.id}/finalize/`,
      {
        method: "POST",
        body: JSON.stringify({
          validation_fingerprint: actualPreview.validation_fingerprint,
          acknowledge_warnings: actualAck,
        }),
      },
    );
    setSelectedActual(updated);
    setMessage("売上実績と経営snapshotを確定しました。");
    await refreshFinance();
  });

  const actualAction = (action: "reopen" | "archive") => run(async () => {
    if (!selectedActual) return;
    const updated = await api<RevenueActualPeriod>(
      `/api/v1/revenue-actual-periods/${selectedActual.id}/${action}/`,
      { method: "POST", body: JSON.stringify({}) },
    );
    setSelectedActual(updated);
    setActualPreview(null);
    setMessage(action === "reopen" ? "売上実績を再オープンしました。" : "売上実績をアーカイブしました。");
    await refreshFinance();
  });

  const loadingAny = locationsQuery.isLoading || categoriesQuery.isLoading || budgetsQuery.isLoading || actualsQuery.isLoading;
  const queryError = locationsQuery.isError || categoriesQuery.isError || budgetsQuery.isError || actualsQuery.isError;
  const budgetEditable = !selectedBudget || !["approved", "archived"].includes(selectedBudget.status);
  const actualEditable = !selectedActual || !["finalized", "archived"].includes(selectedActual.status);

  return (
    <section className="finance-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Financial performance</p>
          <h2>売上・人件費率</h2>
        </div>
      </div>

      <div className="toolbar field-grid finance-filter-grid">
        <label>年<input type="number" min={2000} max={2100} value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} /></label>
        <label>
          拠点
          <select value={location} onChange={(event) => setLocation(event.target.value)}>
            <option value="">選択してください</option>
            {locationsQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
      </div>

      <div className="segmented-control" role="tablist" aria-label="財務管理ビュー">
        {([
          ["summary", "経営サマリー"],
          ["categories", "売上区分"],
          ["budget", "売上予算"],
          ["actual", "売上実績"],
        ] as Array<[FinanceTab, string]>).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? "active" : ""}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {loadingAny ? <p role="status">読み込み中...</p> : null}
      {queryError ? <p className="error">財務管理データの取得に失敗しました。</p> : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
      {message ? <p className="success" role="status">{message}</p> : null}

      {tab === "summary" ? (
        <div className="finance-panel">
          {!location ? <p className="empty-state">拠点を選択すると月次経営サマリーを表示します。</p> : null}
          {performanceQuery.isLoading ? <p role="status">経営サマリーを読み込み中...</p> : null}
          {performanceQuery.isError ? <p className="error">経営サマリーを取得できませんでした。</p> : null}
          {performance ? (
            <>
              <div className="finance-source-strip">
                <span>売上予算: {statusLabel(performance.revenue_budget_source_status)}</span>
                <span>人件費予算: {statusLabel(performance.labor_cost_budget_source_status)}</span>
                <span>概算人件費: {statusLabel(performance.labor_cost_estimate_source_status)}</span>
                <span>売上実績: {statusLabel(performance.status)}</span>
              </div>
              <div className="finance-metric-grid">
                {[
                  ["売上予算", yen(performance.summary.revenue_budget_total)],
                  ["売上実績", yen(performance.summary.revenue_actual_total)],
                  ["売上差異", yen(performance.summary.revenue_variance_amount)],
                  ["売上達成率", percent(performance.summary.revenue_attainment_percent)],
                  ["人件費予算", yen(performance.summary.labor_budget_amount)],
                  ["予定原価", yen(performance.summary.planned_labor_cost)],
                  ["実績概算人件費", yen(performance.summary.actual_labor_cost_estimate)],
                  ["予算人件費率", percent(performance.summary.budget_labor_cost_ratio)],
                  ["予定人件費率", percent(performance.summary.planned_labor_cost_ratio_to_actual_revenue)],
                  ["実績人件費率", percent(performance.summary.actual_labor_cost_ratio)],
                ].map(([label, value]) => <div className="finance-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}
              </div>
              <h3>売上区分別予実</h3>
              {performance.performance_lines.length ? (
                <div className="monthly-grid-wrap"><table className="table">
                  <thead><tr><th scope="col">売上区分</th><th scope="col">予算</th><th scope="col">実績</th><th scope="col">差異</th><th scope="col">達成率</th><th scope="col">状態</th></tr></thead>
                  <tbody>{performance.performance_lines.map((line) => <tr key={line.category_code_snapshot}><td>{line.category_name_snapshot}</td><td>{yen(line.budget_amount)}</td><td>{yen(line.actual_amount)}</td><td>{yen(line.variance_amount)}</td><td>{percent(line.attainment_percent)}</td><td>{line.error_count ? `エラー ${line.error_count}` : line.warning_count ? `警告 ${line.warning_count}` : "正常"}</td></tr>)}</tbody>
                </table></div>
              ) : <p className="empty-state">区分別の売上予実はありません。</p>}
              <div className="issue-columns">
                <section><h3>警告</h3><Issues items={performance.warnings} emptyText="警告はありません。" /></section>
                <section><h3>エラー</h3><Issues items={performance.errors} emptyText="エラーはありません。" /></section>
              </div>
              <dl className="hash-list"><dt>content_hash</dt><dd>{performance.content_hash || "-"}</dd><dt>validation_fingerprint</dt><dd>{performance.validation_fingerprint || "-"}</dd></dl>
            </>
          ) : null}
        </div>
      ) : null}

      {tab === "categories" ? (
        <div className="finance-panel">
          <div className="compact-form field-grid finance-category-form">
            <label>コード<input value={categoryCode} onChange={(event) => setCategoryCode(event.target.value)} /></label>
            <label>名称<input value={categoryName} onChange={(event) => setCategoryName(event.target.value)} /></label>
            <label>短縮名<input value={categoryShortName} onChange={(event) => setCategoryShortName(event.target.value)} /></label>
            <label>表示順<input type="number" min={0} value={categoryOrder} onChange={(event) => setCategoryOrder(Number(event.target.value))} /></label>
            <label>説明<input value={categoryDescription} onChange={(event) => setCategoryDescription(event.target.value)} /></label>
            <div className="actions">
              <button type="button" disabled={busy} onClick={() => void saveCategory()}>{selectedCategory ? "編集" : "作成"}</button>
              <button type="button" className="secondary" disabled={busy} onClick={resetCategory}>新規入力</button>
              <button type="button" className="danger" disabled={busy || !selectedCategory?.is_active} onClick={() => void deactivateCategory()}>無効化</button>
            </div>
          </div>
          {categories.length ? <div className="monthly-grid-wrap"><table className="table">
            <thead><tr><th scope="col">コード</th><th scope="col">名称</th><th scope="col">短縮名</th><th scope="col">表示順</th><th scope="col">状態</th></tr></thead>
            <tbody>{categories.map((category) => <tr key={category.id}><td><button type="button" className="btn-link" onClick={() => chooseCategory(category)}>{category.code}</button></td><td>{category.name}</td><td>{category.short_name}</td><td>{category.display_order}</td><td>{category.is_active ? "有効" : "無効"}</td></tr>)}</tbody>
          </table></div> : <p className="empty-state">売上区分はありません。</p>}
        </div>
      ) : null}

      {tab === "budget" ? (
        <div className="finance-panel">
          <div className="compact-form field-grid">
            <label>Period名<input value={budgetName} disabled={!budgetEditable} onChange={(event) => setBudgetName(event.target.value)} /></label>
            <label>説明<input value={budgetDescription} disabled={!budgetEditable} onChange={(event) => setBudgetDescription(event.target.value)} /></label>
            <div className="actions"><button type="button" disabled={busy || !budgetEditable} onClick={() => void saveBudgetPeriod()}>{selectedBudget ? "編集" : "作成"}</button><button type="button" className="secondary" onClick={resetBudget}>新規入力</button></div>
          </div>
          {budgets.length ? <div className="monthly-grid-wrap"><table className="table">
            <thead><tr><th scope="col">年月</th><th scope="col">拠点</th><th scope="col">名称</th><th scope="col">状態</th><th scope="col">明細数</th></tr></thead>
            <tbody>{budgets.map((period) => <tr key={period.id}><td><button type="button" className="btn-link" onClick={() => void chooseBudget(period)}>{period.year}-{String(period.month).padStart(2, "0")}</button></td><td>{period.location_name}</td><td>{period.name}</td><td>{statusLabel(period.status)}</td><td>{period.line_count}</td></tr>)}</tbody>
          </table></div> : <p className="empty-state">対象月の売上予算はありません。</p>}
          {selectedBudget ? <>
            <h3>売上予算明細</h3>
            {activeCategories.length ? <div className="monthly-grid-wrap"><table className="table finance-entry-table"><thead><tr><th scope="col">売上区分</th><th scope="col">予算額</th></tr></thead><tbody>{activeCategories.map((category) => <tr key={category.id}><td>{category.name}</td><td><label className="sr-only" htmlFor={`budget-${category.id}`}>{category.name}の予算額</label><input id={`budget-${category.id}`} type="number" min={0} disabled={!budgetEditable} value={budgetAmounts[category.id] ?? ""} onChange={(event) => setBudgetAmounts((current) => ({ ...current, [category.id]: event.target.value }))} /></td></tr>)}</tbody></table></div> : <p className="empty-state">有効な売上区分を先に作成してください。</p>}
            <div className="finance-action-row"><button type="button" disabled={busy || !budgetEditable} onClick={() => void saveBudgetLines()}>明細保存</button><button type="button" disabled={busy || selectedBudget.status === "archived"} onClick={() => void previewBudget()}>プレビュー</button><button type="button" onClick={() => window.open(`/api/v1/revenue-budget-periods/${selectedBudget.id}/export-csv/`, "_blank", "noopener")}>CSV出力</button></div>
            {budgetPreview ? <div className="workflow-preview"><div className="finance-metric-grid"><div className="finance-metric"><span>売上予算合計</span><strong>{yen(budgetPreview.summary.budget_total)}</strong></div><div className="finance-metric"><span>判定</span><strong>{budgetPreview.summary.error_count ? "エラー" : budgetPreview.summary.warning_count ? "警告" : "承認可能"}</strong></div></div><div className="issue-columns"><section><h3>警告</h3><Issues items={budgetPreview.warnings} emptyText="警告はありません。" /></section><section><h3>エラー</h3><Issues items={budgetPreview.errors} emptyText="エラーはありません。" /></section></div><label className="checkbox"><input type="checkbox" checked={budgetAck} onChange={(event) => setBudgetAck(event.target.checked)} />warning確認済み</label><div className="actions"><button type="button" disabled={busy || !budgetPreview.can_approve || (budgetPreview.summary.warning_count > 0 && !budgetAck)} onClick={() => void approveBudget()}>承認</button><button type="button" disabled={busy || selectedBudget.status !== "approved"} onClick={() => void budgetAction("reopen")}>再オープン</button><button type="button" disabled={busy || selectedBudget.status === "approved" || selectedBudget.status === "archived"} onClick={() => void budgetAction("archive")}>アーカイブ</button></div><dl className="hash-list"><dt>content_hash</dt><dd>{budgetPreview.content_hash}</dd><dt>validation_fingerprint</dt><dd>{budgetPreview.validation_fingerprint}</dd></dl></div> : null}
          </> : null}
        </div>
      ) : null}

      {tab === "actual" ? (
        <div className="finance-panel">
          <div className="compact-form field-grid">
            <label>Period名<input value={actualName} disabled={!actualEditable} onChange={(event) => setActualName(event.target.value)} /></label>
            <label>説明<input value={actualDescription} disabled={!actualEditable} onChange={(event) => setActualDescription(event.target.value)} /></label>
            <div className="actions"><button type="button" disabled={busy || !actualEditable} onClick={() => void saveActualPeriod()}>{selectedActual ? "編集" : "作成"}</button><button type="button" className="secondary" onClick={resetActual}>新規入力</button></div>
          </div>
          {actuals.length ? <div className="monthly-grid-wrap"><table className="table"><thead><tr><th scope="col">年月</th><th scope="col">拠点</th><th scope="col">名称</th><th scope="col">状態</th><th scope="col">明細数</th></tr></thead><tbody>{actuals.map((period) => <tr key={period.id}><td><button type="button" className="btn-link" onClick={() => void chooseActual(period)}>{period.year}-{String(period.month).padStart(2, "0")}</button></td><td>{period.location_name}</td><td>{period.name}</td><td>{statusLabel(period.status)}</td><td>{period.line_count}</td></tr>)}</tbody></table></div> : <p className="empty-state">対象月の売上実績はありません。</p>}
          {selectedActual ? <>
            <h3>売上実績明細</h3>
            {activeCategories.length ? <div className="monthly-grid-wrap"><table className="table finance-entry-table"><thead><tr><th scope="col">売上区分</th><th scope="col">実績額</th></tr></thead><tbody>{activeCategories.map((category) => <tr key={category.id}><td>{category.name}</td><td><label className="sr-only" htmlFor={`actual-${category.id}`}>{category.name}の実績額</label><input id={`actual-${category.id}`} type="number" min={0} disabled={!actualEditable} value={actualAmounts[category.id] ?? ""} onChange={(event) => setActualAmounts((current) => ({ ...current, [category.id]: event.target.value }))} /></td></tr>)}</tbody></table></div> : <p className="empty-state">有効な売上区分を先に作成してください。</p>}
            <div className="finance-action-row"><button type="button" disabled={busy || !actualEditable} onClick={() => void saveActualLines()}>明細保存</button><button type="button" disabled={busy || selectedActual.status === "archived"} onClick={() => void previewActual()}>{selectedActual.status === "finalized" ? "確定値表示" : "プレビュー"}</button><button type="button" onClick={() => window.open(`/api/v1/revenue-actual-periods/${selectedActual.id}/export-csv/`, "_blank", "noopener")}>CSV出力</button></div>
            {actualPreview ? <div className="workflow-preview"><div className="finance-source-strip"><span>売上予算: {statusLabel(actualPreview.revenue_budget_source_status)}</span><span>人件費予算: {statusLabel(actualPreview.labor_cost_budget_source_status)}</span><span>概算人件費: {statusLabel(actualPreview.labor_cost_estimate_source_status)}</span></div><div className="finance-metric-grid">{[["売上予算", yen(actualPreview.summary.revenue_budget_total)], ["売上実績", yen(actualPreview.summary.revenue_actual_total)], ["売上差異", yen(actualPreview.summary.revenue_variance_amount)], ["売上達成率", percent(actualPreview.summary.revenue_attainment_percent)], ["予定人件費率", percent(actualPreview.summary.planned_labor_cost_ratio_to_actual_revenue)], ["実績人件費率", percent(actualPreview.summary.actual_labor_cost_ratio)]].map(([label, value]) => <div className="finance-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="issue-columns"><section><h3>警告</h3><Issues items={actualPreview.warnings} emptyText="警告はありません。" /></section><section><h3>エラー</h3><Issues items={actualPreview.errors} emptyText="エラーはありません。" /></section></div><label className="checkbox"><input type="checkbox" checked={actualAck} onChange={(event) => setActualAck(event.target.checked)} />warning確認済み</label><div className="actions"><button type="button" disabled={busy || !actualPreview.can_finalize || (actualPreview.summary.warning_count > 0 && !actualAck)} onClick={() => void finalizeActual()}>確定</button><button type="button" disabled={busy || selectedActual.status !== "finalized"} onClick={() => void actualAction("reopen")}>再オープン</button><button type="button" disabled={busy || selectedActual.status === "finalized" || selectedActual.status === "archived"} onClick={() => void actualAction("archive")}>アーカイブ</button></div><dl className="hash-list"><dt>content_hash</dt><dd>{actualPreview.content_hash}</dd><dt>validation_fingerprint</dt><dd>{actualPreview.validation_fingerprint}</dd></dl></div> : null}
          </> : null}
        </div>
      ) : null}
    </section>
  );
}
