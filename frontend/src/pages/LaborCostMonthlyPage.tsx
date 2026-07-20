import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type {
  AttendanceClosingPeriod,
  LaborCostEstimatePeriod,
  LaborCostEstimatePreview,
  Location,
  Paginated,
} from "../lib/types";

const today = new Date();

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    draft: "下書き",
    review: "確認中",
    finalized: "概算確定済み",
    reopened: "再オープン",
    archived: "アーカイブ",
    closed: "締め済み",
    live: "未締めpreview",
  };
  return labels[value] ?? value;
}

function issueCodes(items: Array<{ code: string }>) {
  return items.map((item) => item.code).join(" ");
}

export function LaborCostMonthlyPage() {
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [location, setLocation] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<LaborCostEstimatePeriod | null>(null);
  const [preview, setPreview] = useState<LaborCostEstimatePreview | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [attendanceClosingPeriod, setAttendanceClosingPeriod] = useState("");
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

  const closingQueryString = useMemo(() => {
    const params = new URLSearchParams({ year: String(year), month: String(month), is_active: "true" });
    if (location) params.set("location", location);
    return params.toString();
  }, [location, month, year]);

  const locationsQuery = useQuery({
    queryKey: ["labor-cost-monthly-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
    enabled: canManage,
  });
  const periodsQuery = useQuery({
    queryKey: ["labor-cost-estimate-periods", queryString],
    queryFn: () => api<Paginated<LaborCostEstimatePeriod>>(`/api/v1/labor-cost-estimate-periods/?${queryString}`),
    enabled: canManage,
  });
  const closingPeriodsQuery = useQuery({
    queryKey: ["labor-cost-closing-periods", closingQueryString],
    queryFn: () => api<Paginated<AttendanceClosingPeriod>>(`/api/v1/attendance-closing-periods/?${closingQueryString}`),
    enabled: canManage,
  });

  if (!loading && !canManage) return <Navigate to="/403" replace />;

  const choosePeriod = (period: LaborCostEstimatePeriod) => {
    setSelected(period);
    setPreview(null);
    setName(period.name);
    setDescription(period.description);
    setAttendanceClosingPeriod(period.attendance_closing_period ?? "");
    setAcknowledgeWarnings(false);
    setManagerNote("");
    setMessage("");
    setError("");
  };

  const createPeriod = async () => {
    if (!location) {
      setError("拠点を選択してください。");
      return;
    }
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const payload = {
        location,
        year,
        month,
        attendance_closing_period: attendanceClosingPeriod || null,
        name,
        description,
      };
      const created = await api<LaborCostEstimatePeriod>("/api/v1/labor-cost-estimate-periods/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      choosePeriod(created);
      setMessage("概算人件費periodを作成しました。");
      await queryClient.invalidateQueries({ queryKey: ["labor-cost-estimate-periods"] });
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
      const updated = await api<LaborCostEstimatePeriod>(`/api/v1/labor-cost-estimate-periods/${selected.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          attendance_closing_period: attendanceClosingPeriod || null,
          name,
          description,
        }),
      });
      setSelected(updated);
      setMessage("概算人件費periodを更新しました。");
      await queryClient.invalidateQueries({ queryKey: ["labor-cost-estimate-periods"] });
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
      const data = await api<LaborCostEstimatePreview>(`/api/v1/labor-cost-estimate-periods/${selected.id}/preview/`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setPreview(data);
      setMessage("previewを更新しました。");
      await queryClient.invalidateQueries({ queryKey: ["labor-cost-estimate-periods"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "previewに失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const finalize = async () => {
    if (!selected || !preview) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const updated = await api<LaborCostEstimatePeriod>(`/api/v1/labor-cost-estimate-periods/${selected.id}/finalize/`, {
        method: "POST",
        body: JSON.stringify({
          acknowledge_warnings: acknowledgeWarnings,
          validation_fingerprint: preview.validation_fingerprint,
          manager_note: managerNote,
        }),
      });
      setSelected(updated);
      setMessage("概算人件費snapshotを確定しました。");
      await queryClient.invalidateQueries({ queryKey: ["labor-cost-estimate-periods"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "finalizeに失敗しました。");
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
      const updated = await api<LaborCostEstimatePeriod>(`/api/v1/labor-cost-estimate-periods/${selected.id}/${action}/`, {
        method: "POST",
        body: JSON.stringify({ manager_note: managerNote }),
      });
      setSelected(updated);
      setMessage(action === "reopen" ? "再オープンしました。" : "アーカイブしました。");
      await queryClient.invalidateQueries({ queryKey: ["labor-cost-estimate-periods"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "操作に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const exportCsv = () => {
    if (!selected) return;
    window.open(`/api/v1/labor-cost-estimate-periods/${selected.id}/export-csv/`, "_blank", "noopener");
  };

  const periods = periodsQuery.data?.results ?? [];

  return (
    <section className="card monthly-page labor-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Labor cost estimate</p>
          <h2>概算人件費</h2>
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
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          状態
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">すべて</option>
            <option value="draft">下書き</option>
            <option value="review">確認中</option>
            <option value="finalized">概算確定済み</option>
            <option value="reopened">再オープン</option>
          </select>
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      <div className="compact-form field-grid">
        <label>
          Period名
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          勤怠締めperiod
          <select value={attendanceClosingPeriod} onChange={(event) => setAttendanceClosingPeriod(event.target.value)}>
            <option value="">自動選択</option>
            {closingPeriodsQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.location_name} {item.year}-{String(item.month).padStart(2, "0")} {statusLabel(item.status)}
              </option>
            ))}
          </select>
        </label>
        <label>
          説明
          <input value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <div className="actions">
          <button type="button" disabled={isSubmitting} onClick={() => void createPeriod()}>
            Period作成
          </button>
          <button type="button" disabled={isSubmitting || !selected} onClick={() => void updatePeriod()}>
            Period編集
          </button>
        </div>
      </div>
      {periodsQuery.isLoading ? <p>読み込み中...</p> : null}
      {periodsQuery.isError ? <p className="error">Period一覧の取得に失敗しました。</p> : null}
      {!periodsQuery.isLoading && !periodsQuery.isError && periods.length === 0 ? (
        <p className="subtle-text">概算人件費periodはありません。</p>
      ) : null}
      <div className="monthly-layout">
        <div className="monthly-grid-wrap">
          {periods.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>年月</th>
                  <th>拠点</th>
                  <th>状態</th>
                  <th>勤怠締め</th>
                  <th>content_hash</th>
                  <th>snapshot</th>
                </tr>
              </thead>
              <tbody>
                {periods.map((period) => (
                  <tr key={period.id}>
                    <td>
                      <button type="button" className="btn-link" onClick={() => choosePeriod(period)}>
                        {period.year}-{String(period.month).padStart(2, "0")}
                      </button>
                    </td>
                    <td>{period.location_name}</td>
                    <td>{statusLabel(period.status)}</td>
                    <td>{period.attendance_closing_period_status || "-"}</td>
                    <td>{period.content_hash ? period.content_hash.slice(0, 12) : "-"}</td>
                    <td>{period.record_snapshot_count} / {period.staff_summary_count} / {period.allowance_snapshot_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
        {selected ? (
          <aside className="edit-panel">
            <h3>{selected.name}</h3>
            <p className="subtle-text">{selected.location_name} / {statusLabel(selected.status)}</p>
            <dl>
              <dt>content_hash</dt>
              <dd>{selected.content_hash || "-"}</dd>
              <dt>validation_fingerprint</dt>
              <dd>{preview?.validation_fingerprint ?? selected.validation_fingerprint ?? "-"}</dd>
              <dt>source</dt>
              <dd>{preview ? `${preview.source_status} / ${preview.attendance_closing_status}` : "-"}</dd>
            </dl>
            <div className="actions">
              <button type="button" disabled={isSubmitting} onClick={() => void runPreview()}>
                preview
              </button>
              <button type="button" disabled={isSubmitting} onClick={exportCsv}>
                CSV出力
              </button>
            </div>
            <section className="inline-alert">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={acknowledgeWarnings}
                  onChange={(event) => setAcknowledgeWarnings(event.target.checked)}
                />
                warning確認済み
              </label>
              <label>
                管理メモ
                <input value={managerNote} onChange={(event) => setManagerNote(event.target.value)} />
              </label>
              <div className="actions">
                <button type="button" disabled={isSubmitting || !preview} onClick={() => void finalize()}>
                  finalize
                </button>
                <button type="button" disabled={isSubmitting} onClick={() => void periodAction("reopen")}>
                  reopen
                </button>
                <button type="button" disabled={isSubmitting} onClick={() => void periodAction("archive")}>
                  archive
                </button>
              </div>
            </section>
          </aside>
        ) : null}
      </div>
      {preview ? (
        <div className="preview-block">
          <div className="summary-strip">
            <span>スタッフ {preview.summary.staff_count}</span>
            <span>勤務分 {preview.summary.worked_minutes}</span>
            <span>基本概算 {preview.summary.base_pay_total}</span>
            <span>手当概算 {preview.summary.allowance_total}</span>
            <span>概算合計 {preview.summary.estimated_total}</span>
            <span>warning {preview.summary.warning_count}</span>
            <span>error {preview.summary.error_count}</span>
          </div>
          {preview.issues.length ? (
            <ul className="issue-list">
              {preview.issues.map((issue) => (
                <li key={`${issue.severity}-${issue.code}`}>{issue.severity}: {issue.code}</li>
              ))}
            </ul>
          ) : null}
          <h3>staff summary</h3>
          <table className="table">
            <thead>
              <tr>
                <th>スタッフ</th>
                <th>雇用区分</th>
                <th>勤務日数</th>
                <th>勤務時間</th>
                <th>基本概算</th>
                <th>手当概算</th>
                <th>概算合計</th>
                <th>warning/error</th>
              </tr>
            </thead>
            <tbody>
              {preview.staff_summaries.map((item) => (
                <tr key={item.staff}>
                  <td>{item.employee_code_snapshot} {item.staff_display_name_snapshot}</td>
                  <td>{item.employment_type_snapshot}</td>
                  <td>{item.worked_days}</td>
                  <td>{item.worked_hours_decimal}</td>
                  <td>{item.base_pay_total}</td>
                  <td>{item.allowance_total}</td>
                  <td>{item.estimated_total}</td>
                  <td>{item.warning_count}/{item.error_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>record detail</h3>
          <table className="table">
            <thead>
              <tr>
                <th>勤務日</th>
                <th>スタッフ</th>
                <th>勤務分</th>
                <th>基本概算</th>
                <th>手当概算</th>
                <th>概算合計</th>
                <th>warning</th>
                <th>error</th>
              </tr>
            </thead>
            <tbody>
              {preview.record_snapshots.slice(0, 80).map((item) => (
                <tr key={`${item.staff}-${item.work_date}`}>
                  <td>{item.work_date}</td>
                  <td>{item.employee_code ?? item.employee_code_snapshot} {item.staff_display_name ?? item.staff_display_name_snapshot}</td>
                  <td>{item.worked_minutes}</td>
                  <td>{item.base_pay}</td>
                  <td>{item.allowance_total}</td>
                  <td>{item.estimated_total}</td>
                  <td>{issueCodes(item.warnings)}</td>
                  <td>{issueCodes(item.errors)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>allowance detail</h3>
          <table className="table">
            <thead>
              <tr>
                <th>スタッフ</th>
                <th>コード</th>
                <th>種別</th>
                <th>数量</th>
                <th>概算額</th>
                <th>warning</th>
              </tr>
            </thead>
            <tbody>
              {preview.allowance_snapshots.map((item) => (
                <tr key={`${item.staff}-${item.code_snapshot}`}>
                  <td>{item.employee_code_snapshot} {item.staff_display_name_snapshot}</td>
                  <td>{item.code_snapshot} {item.name_snapshot}</td>
                  <td>{item.allowance_type_snapshot}</td>
                  <td>{item.quantity}</td>
                  <td>{item.estimated_amount}</td>
                  <td>{issueCodes(item.warnings)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
