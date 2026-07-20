import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type {
  LaborCostBudgetPeriod,
  LaborCostBudgetPreview,
  LaborCostIssue,
  Location,
  Paginated,
} from "../lib/types";

const today = new Date();

const statusLabels: Record<string, string> = {
  draft: "下書き",
  review: "確認中",
  approved: "承認済み",
  reopened: "再オープン",
  archived: "アーカイブ",
  published: "公開シフト",
  confirmed: "確定シフト",
  unavailable: "利用不可",
  finalized: "概算確定済み",
  normal: "正常",
  warning: "警戒",
  critical: "超過",
};

function statusLabel(value: string) {
  return statusLabels[value] ?? value;
}

function yen(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "-";
  return new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY", maximumFractionDigits: 0 }).format(
    Number(value),
  );
}

function percent(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "-";
  return `${Number(value).toLocaleString("ja-JP", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function issueCodes(items: LaborCostIssue[]) {
  return items.map((item) => item.code).join(" ");
}

export function LaborCostBudgetPage() {
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const [year, setYear] = useState(Number(searchParams.get("year")) || today.getFullYear());
  const [month, setMonth] = useState(Number(searchParams.get("month")) || today.getMonth() + 1);
  const [location, setLocation] = useState(searchParams.get("location") ?? "");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<LaborCostBudgetPeriod | null>(null);
  const [preview, setPreview] = useState<LaborCostBudgetPreview | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [budgetAmount, setBudgetAmount] = useState("0");
  const [warningThreshold, setWarningThreshold] = useState("90");
  const [criticalThreshold, setCriticalThreshold] = useState("100");
  const [acknowledgeWarnings, setAcknowledgeWarnings] = useState(false);
  const [managerNote, setManagerNote] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ year: String(year), month: String(month), is_active: "true" });
    if (location) params.set("location", location);
    if (status) params.set("status", status);
    return params.toString();
  }, [location, month, status, year]);

  const locationsQuery = useQuery({
    queryKey: ["labor-budget-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
    enabled: canManage,
  });
  const periodsQuery = useQuery({
    queryKey: ["labor-cost-budget-periods", queryString],
    queryFn: () => api<Paginated<LaborCostBudgetPeriod>>(`/api/v1/labor-cost-budget-periods/?${queryString}`),
    enabled: canManage,
  });

  const choosePeriod = (period: LaborCostBudgetPeriod) => {
    setSelected(period);
    setPreview(null);
    setName(period.name);
    setDescription(period.description);
    setBudgetAmount(period.budget_amount);
    setWarningThreshold(period.warning_threshold_percent);
    setCriticalThreshold(period.critical_threshold_percent);
    setAcknowledgeWarnings(false);
    setManagerNote("");
    setMessage("");
    setError("");
  };

  if (!loading && !canManage) return <Navigate to="/403" replace />;

  const refreshPeriods = () => queryClient.invalidateQueries({ queryKey: ["labor-cost-budget-periods"] });

  const createPeriod = async () => {
    if (!location) {
      setError("拠点を選択してください。");
      return;
    }
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const created = await api<LaborCostBudgetPeriod>("/api/v1/labor-cost-budget-periods/", {
        method: "POST",
        body: JSON.stringify({
          location,
          year,
          month,
          name,
          description,
          budget_amount: budgetAmount,
          warning_threshold_percent: warningThreshold,
          critical_threshold_percent: criticalThreshold,
        }),
      });
      choosePeriod(created);
      setMessage("人件費予算periodを作成しました。");
      await refreshPeriods();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "作成に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const updatePeriod = async () => {
    if (!selected) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const updated = await api<LaborCostBudgetPeriod>(`/api/v1/labor-cost-budget-periods/${selected.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          name,
          description,
          budget_amount: budgetAmount,
          warning_threshold_percent: warningThreshold,
          critical_threshold_percent: criticalThreshold,
        }),
      });
      setSelected(updated);
      setMessage("人件費予算periodを更新しました。");
      await refreshPeriods();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "更新に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const runPreview = async () => {
    if (!selected) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const approved = selected.status === "approved";
      const data = await api<LaborCostBudgetPreview>(
        `/api/v1/labor-cost-budget-periods/${selected.id}/${approved ? "variance" : "preview"}/`,
        approved ? undefined : { method: "POST", body: JSON.stringify({}) },
      );
      setPreview(data);
      setMessage(approved ? "最新の予実比較を取得しました。" : "予定原価previewを更新しました。");
      await refreshPeriods();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "previewに失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const approve = async () => {
    if (!selected || !preview) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const updated = await api<LaborCostBudgetPeriod>(
        `/api/v1/labor-cost-budget-periods/${selected.id}/approve/`,
        {
          method: "POST",
          body: JSON.stringify({
            acknowledge_warnings: acknowledgeWarnings,
            validation_fingerprint: preview.validation_fingerprint,
            manager_note: managerNote,
          }),
        },
      );
      setSelected(updated);
      setMessage("予算と予定原価snapshotを承認しました。");
      await refreshPeriods();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "承認に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const periodAction = async (action: "reopen" | "archive") => {
    if (!selected) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const updated = await api<LaborCostBudgetPeriod>(
        `/api/v1/labor-cost-budget-periods/${selected.id}/${action}/`,
        { method: "POST", body: JSON.stringify({ manager_note: managerNote }) },
      );
      setSelected(updated);
      setPreview(null);
      setMessage(action === "reopen" ? "予算periodを再オープンしました。" : "予算periodをアーカイブしました。");
      await refreshPeriods();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "操作に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const exportCsv = () => {
    if (selected) window.open(`/api/v1/labor-cost-budget-periods/${selected.id}/export-csv/`, "_blank", "noopener");
  };

  const periods = periodsQuery.data?.results ?? [];
  const editable = selected ? !["approved", "archived"].includes(selected.status) : true;

  return (
    <section className="card monthly-page labor-page labor-budget-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Labor cost budget variance</p>
          <h2>人件費予算・予実</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>
          年
          <input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} />
        </label>
        <label>
          月
          <input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} />
        </label>
        <label>
          拠点
          <select value={location} onChange={(event) => setLocation(event.target.value)}>
            <option value="">すべて</option>
            {locationsQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
        </label>
        <label>
          状態
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">すべて</option>
            <option value="draft">下書き</option>
            <option value="review">確認中</option>
            <option value="approved">承認済み</option>
            <option value="reopened">再オープン</option>
          </select>
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      <div className="compact-form field-grid budget-form-grid">
        <label>
          Period名
          <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          予算額
          <input type="number" min={0} value={budgetAmount} disabled={!editable} onChange={(event) => setBudgetAmount(event.target.value)} />
        </label>
        <label>
          警戒閾値（%）
          <input type="number" min={0} value={warningThreshold} disabled={!editable} onChange={(event) => setWarningThreshold(event.target.value)} />
        </label>
        <label>
          超過閾値（%）
          <input type="number" min={0} max={999.99} value={criticalThreshold} disabled={!editable} onChange={(event) => setCriticalThreshold(event.target.value)} />
        </label>
        <label>
          説明
          <input value={description} disabled={!editable} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <div className="actions">
          <button type="button" disabled={isSubmitting || Boolean(selected)} onClick={() => void createPeriod()}>作成</button>
          <button type="button" disabled={isSubmitting || !selected || !editable} onClick={() => void updatePeriod()}>編集</button>
          <button type="button" className="secondary" onClick={() => { setSelected(null); setPreview(null); setName(""); }}>新規入力</button>
        </div>
      </div>
      {periodsQuery.isLoading ? <p>読み込み中...</p> : null}
      {periodsQuery.isError ? <p className="error">予算period一覧の取得に失敗しました。</p> : null}
      {!periodsQuery.isLoading && !periodsQuery.isError && periods.length === 0 ? (
        <p className="empty-state">対象年月の人件費予算はありません。</p>
      ) : null}
      {periods.length ? (
        <div className="monthly-grid-wrap">
          <table className="table">
            <thead><tr><th>年月</th><th>拠点</th><th>状態</th><th>予算</th><th>閾値</th><th>source</th><th>hash</th></tr></thead>
            <tbody>
              {periods.map((period) => (
                <tr key={period.id}>
                  <td><button type="button" className="btn-link" onClick={() => choosePeriod(period)}>{period.year}-{String(period.month).padStart(2, "0")}</button></td>
                  <td>{period.location_name}</td>
                  <td>{statusLabel(period.status)}</td>
                  <td>{yen(period.budget_amount)}</td>
                  <td>{period.warning_threshold_percent}% / {period.critical_threshold_percent}%</td>
                  <td>{period.source_publication ? "公開シフト" : period.source_monthly_shift_plan ? "確定シフト" : "-"}</td>
                  <td>{period.content_hash ? period.content_hash.slice(0, 12) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {selected ? (
        <div className="budget-action-bar">
          <div>
            <strong>{selected.name}</strong>
            <span>{selected.location_name} / {statusLabel(selected.status)}</span>
          </div>
          <div className="actions">
            <button type="button" disabled={isSubmitting || selected.status === "archived"} onClick={() => void runPreview()}>{selected.status === "approved" ? "比較更新" : "プレビュー"}</button>
            <button type="button" disabled={isSubmitting} onClick={exportCsv}>CSV出力</button>
          </div>
          <label className="checkbox">
            <input type="checkbox" checked={acknowledgeWarnings} onChange={(event) => setAcknowledgeWarnings(event.target.checked)} />
            warning確認済み
          </label>
          <label>
            管理メモ
            <input value={managerNote} onChange={(event) => setManagerNote(event.target.value)} />
          </label>
          <div className="actions">
            <button
              type="button"
              disabled={
                isSubmitting ||
                !preview ||
                !preview.can_approve ||
                (Boolean(preview.summary.approval_warning_count) && !acknowledgeWarnings)
              }
              onClick={() => void approve()}
            >
              承認
            </button>
            <button type="button" disabled={isSubmitting || selected.status !== "approved"} onClick={() => void periodAction("reopen")}>再オープン</button>
            <button type="button" disabled={isSubmitting || selected.status === "approved" || selected.status === "archived"} onClick={() => void periodAction("archive")}>アーカイブ</button>
          </div>
          <dl className="hash-list">
            <dt>content_hash</dt><dd>{preview?.content_hash ?? selected.content_hash ?? "-"}</dd>
            <dt>validation_fingerprint</dt><dd>{preview?.validation_fingerprint ?? selected.validation_fingerprint ?? "-"}</dd>
          </dl>
        </div>
      ) : null}
      {preview ? (
        <div className="preview-block budget-preview">
          <div className="budget-summary-grid">
            {[
              ["予算", yen(preview.summary.budget_amount)],
              ["予定原価", yen(preview.summary.planned_total)],
              ["実績概算", yen(preview.summary.actual_estimated_total)],
              ["予定対予算差異", yen(preview.summary.planned_budget_variance_amount)],
              ["実績対予算差異", yen(preview.summary.actual_budget_variance_amount)],
              ["実績対予定差異", yen(preview.summary.actual_plan_variance_amount)],
              ["予定予算消化率", `${percent(preview.summary.planned_budget_ratio_percent)} / ${statusLabel(preview.summary.planned_budget_status)}`],
              ["実績予算消化率", `${percent(preview.summary.actual_budget_ratio_percent)} / ${statusLabel(preview.summary.actual_budget_status)}`],
            ].map(([label, value]) => (
              <div className="budget-metric" key={label}><span>{label}</span><strong>{value}</strong></div>
            ))}
          </div>
          <div className="source-line">
            <span>予定source: {statusLabel(preview.plan_source)}</span>
            <span>実績source: {statusLabel(preview.actual_source_status)}</span>
            <span className={`budget-status status-${preview.summary.planned_budget_status}`}>予定: {statusLabel(preview.summary.planned_budget_status)}</span>
            <span className={`budget-status status-${preview.summary.actual_budget_status}`}>実績: {statusLabel(preview.summary.actual_budget_status)}</span>
          </div>
          <div className="issue-columns">
            <section>
              <h3>承認判定issues</h3>
              {preview.approval_issues.length ? <ul className="issue-list">{preview.approval_issues.map((issue, index) => <li key={`${issue.code}-${index}`}><strong>{issue.severity}: {issue.code}</strong><span>{issue.message}</span></li>)}</ul> : <p className="subtle-text">承認判定issueはありません。</p>}
            </section>
            <section>
              <h3>比較issues</h3>
              {preview.comparison_issues.length ? <ul className="issue-list">{preview.comparison_issues.map((issue, index) => <li key={`${issue.code}-${index}`}><strong>{issue.severity}: {issue.code}</strong><span>{issue.message}</span></li>)}</ul> : <p className="subtle-text">比較issueはありません。</p>}
            </section>
          </div>
          <h3>スタッフ別予実</h3>
          <div className="monthly-grid-wrap"><table className="table">
            <thead><tr><th>スタッフ</th><th>予定分</th><th>予定原価</th><th>実績分</th><th>実績概算</th><th>差異</th><th>差異率</th></tr></thead>
            <tbody>{preview.staff_summaries.map((item) => <tr key={item.staff}><td>{item.employee_code_snapshot} {item.staff_display_name_snapshot}</td><td>{item.planned_worked_minutes}</td><td>{yen(item.planned_total)}</td><td>{item.actual_worked_minutes}</td><td>{yen(item.actual_estimated_total)}</td><td>{yen(item.actual_plan_variance_amount)}</td><td>{percent(item.actual_plan_variance_percent)}</td></tr>)}</tbody>
          </table></div>
          <h3>日別予実</h3>
          <div className="monthly-grid-wrap"><table className="table">
            <thead><tr><th>勤務日</th><th>予定人数</th><th>予定分</th><th>予定原価</th><th>実績人数</th><th>実績分</th><th>実績概算</th><th>差異</th></tr></thead>
            <tbody>{preview.daily_summaries.map((item) => <tr key={item.work_date}><td>{item.work_date}</td><td>{item.planned_staff_count}</td><td>{item.planned_worked_minutes}</td><td>{yen(item.planned_total)}</td><td>{item.actual_staff_count}</td><td>{item.actual_worked_minutes}</td><td>{yen(item.actual_estimated_total)}</td><td>{yen(item.actual_plan_variance_amount)}</td></tr>)}</tbody>
          </table></div>
          <h3>予定原価明細</h3>
          <div className="monthly-grid-wrap"><table className="table">
            <thead><tr><th>勤務日</th><th>スタッフ</th><th>勤務分</th><th>基本原価</th><th>日次手当</th><th>合計</th><th>warning</th><th>error</th></tr></thead>
            <tbody>{preview.plan_records.slice(0, 200).map((item) => <tr key={`${item.staff}-${item.work_date}`}><td>{item.work_date}</td><td>{item.employee_code ?? item.employee_code_snapshot} {item.staff_display_name ?? item.staff_display_name_snapshot}</td><td>{item.planned_worked_minutes}</td><td>{yen(item.planned_base_pay)}</td><td>{yen(item.planned_daily_allowance)}</td><td>{yen(item.planned_total)}</td><td>{issueCodes(item.warnings)}</td><td>{issueCodes(item.errors)}</td></tr>)}</tbody>
          </table></div>
          <h3>予定手当</h3>
          <div className="monthly-grid-wrap"><table className="table">
            <thead><tr><th>スタッフ</th><th>手当</th><th>種別</th><th>数量</th><th>単価</th><th>予定額</th><th>warning</th></tr></thead>
            <tbody>{preview.allowance_snapshots.map((item) => <tr key={`${item.staff}-${item.code_snapshot}`}><td>{item.employee_code_snapshot} {item.staff_display_name_snapshot}</td><td>{item.code_snapshot} {item.name_snapshot}</td><td>{item.allowance_type_snapshot}</td><td>{item.quantity}</td><td>{yen(item.amount_snapshot)}</td><td>{yen(item.planned_amount)}</td><td>{issueCodes(item.warnings)}</td></tr>)}</tbody>
          </table></div>
        </div>
      ) : null}
    </section>
  );
}
