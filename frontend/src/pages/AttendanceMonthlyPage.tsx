import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import { offsetToLabel } from "../lib/timeOffsets";
import type {
  AttendanceClosingPeriod,
  AttendanceClosingPreview,
  AttendanceClosingPreviewItem,
  Location,
  Paginated,
} from "../lib/types";

const today = new Date();

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    draft: "下書き",
    review: "確認中",
    closed: "締め済み",
    reopened: "再オープン",
    archived: "アーカイブ",
  };
  return labels[status] ?? status;
}

function offsetRange(item: AttendanceClosingPreviewItem) {
  if (item.scheduled_start_offset_minutes == null || item.scheduled_end_offset_minutes == null) return "-";
  return `${offsetToLabel(item.scheduled_start_offset_minutes)}~${offsetToLabel(item.scheduled_end_offset_minutes)}`;
}

export function AttendanceMonthlyPage() {
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [location, setLocation] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<AttendanceClosingPeriod | null>(null);
  const [preview, setPreview] = useState<AttendanceClosingPreview | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
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
    queryKey: ["attendance-closing-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
    enabled: canView,
  });
  const periodsQuery = useQuery({
    queryKey: ["attendance-closing-periods", queryString],
    queryFn: () => api<Paginated<AttendanceClosingPeriod>>(`/api/v1/attendance-closing-periods/?${queryString}`),
    enabled: canView,
  });
  const periods = periodsQuery.data?.results ?? [];

  if (!loading && !canView) return <Navigate to="/403" replace />;

  const choosePeriod = (period: AttendanceClosingPeriod) => {
    setSelected(period);
    setPreview(null);
    setName(period.name);
    setDescription(period.description);
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
      const created = await api<AttendanceClosingPeriod>("/api/v1/attendance-closing-periods/", {
        method: "POST",
        body: JSON.stringify({ location, year, month, name, description }),
      });
      setMessage("Periodを作成しました。");
      choosePeriod(created);
      await queryClient.invalidateQueries({ queryKey: ["attendance-closing-periods"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Period作成に失敗しました。");
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
      const updated = await api<AttendanceClosingPeriod>(`/api/v1/attendance-closing-periods/${selected.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ name, description }),
      });
      setSelected(updated);
      setMessage("Periodを更新しました。");
      await queryClient.invalidateQueries({ queryKey: ["attendance-closing-periods"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Period更新に失敗しました。");
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
      const data = await api<AttendanceClosingPreview>(`/api/v1/attendance-closing-periods/${selected.id}/preview/`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setPreview(data);
      setMessage("previewを更新しました。");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "previewに失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const closePeriod = async () => {
    if (!selected || !preview) return;
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      const closed = await api<AttendanceClosingPeriod>(`/api/v1/attendance-closing-periods/${selected.id}/close/`, {
        method: "POST",
        body: JSON.stringify({
          acknowledge_warnings: acknowledgeWarnings,
          validation_fingerprint: preview.validation_fingerprint,
          manager_note: managerNote,
        }),
      });
      setSelected(closed);
      setMessage("月次勤怠を締めました。");
      await queryClient.invalidateQueries({ queryKey: ["attendance-closing-periods"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "closeに失敗しました。");
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
      const updated = await api<AttendanceClosingPeriod>(`/api/v1/attendance-closing-periods/${selected.id}/${action}/`, {
        method: "POST",
        body: JSON.stringify({ manager_note: managerNote }),
      });
      setSelected(updated);
      setMessage(action === "reopen" ? "再オープンしました。" : "アーカイブしました。");
      await queryClient.invalidateQueries({ queryKey: ["attendance-closing-periods"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "操作に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const exportCsv = () => {
    if (!selected) return;
    window.open(`/api/v1/attendance-closing-periods/${selected.id}/export-csv/`, "_blank", "noopener");
  };

  const issueItems = preview?.items.filter((item) => item.issues.length > 0) ?? [];

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Attendance closing</p>
          <h2>月次勤怠締め</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>年<input type="number" value={year} onChange={(event) => { setYear(Number(event.target.value)); setSelected(null); }} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => { setMonth(Number(event.target.value)); setSelected(null); }} /></label>
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setSelected(null); }}><option value="">すべて</option>{locationsQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>状態<select value={status} onChange={(event) => { setStatus(event.target.value); setSelected(null); }}><option value="">すべて</option><option value="draft">下書き</option><option value="review">確認中</option><option value="closed">締め済み</option><option value="reopened">再オープン</option></select></label>
      </div>
      {periodsQuery.isLoading ? <p>読み込み中...</p> : null}
      {periodsQuery.isError ? <p className="error">Period一覧の取得に失敗しました。</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {canManage ? (
        <div className="compact-form field-grid">
          <label>Period名<input value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>説明<input value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <button type="button" disabled={isSubmitting} onClick={() => void createPeriod()}>Period作成</button>
          <button type="button" disabled={isSubmitting || !selected || selected.status === "archived"} onClick={() => void updatePeriod()}>Period編集</button>
        </div>
      ) : null}
      {!periodsQuery.isLoading && !periodsQuery.isError && periods.length === 0 ? <p className="subtle-text">Periodはありません。</p> : null}
      <div className="monthly-layout">
        <div className="monthly-grid-wrap">
          {periods.length ? (
            <table className="table">
              <thead><tr><th>年月</th><th>拠点</th><th>状態</th><th>hash</th><th>snapshot</th><th>summary</th></tr></thead>
              <tbody>
                {periods.map((period) => (
                  <tr key={period.id}>
                    <td><button type="button" className="btn-link" onClick={() => choosePeriod(period)}>{period.year}-{String(period.month).padStart(2, "0")}</button></td>
                    <td>{period.location_name}</td>
                    <td>{statusLabel(period.status)}</td>
                    <td>{period.content_hash ? period.content_hash.slice(0, 12) : "-"}</td>
                    <td>{period.snapshot_count}</td>
                    <td>{period.staff_summary_count}</td>
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
              <dt>content_hash</dt><dd>{selected.content_hash || "-"}</dd>
              <dt>validation_fingerprint</dt><dd>{preview?.validation_fingerprint ?? (selected.validation_fingerprint || "-")}</dd>
              <dt>closed_at</dt><dd>{selected.closed_at ?? "-"}</dd>
              <dt>reopened_at</dt><dd>{selected.reopened_at ?? "-"}</dd>
            </dl>
            <div className="actions">
              <button type="button" disabled={isSubmitting} onClick={() => void runPreview()}>preview</button>
              <button type="button" disabled={isSubmitting} onClick={exportCsv}>CSV出力</button>
            </div>
            {canManage ? (
              <section className="inline-alert">
                <label className="checkbox"><input type="checkbox" checked={acknowledgeWarnings} onChange={(event) => setAcknowledgeWarnings(event.target.checked)} />warning確認済み</label>
                <label>管理メモ<textarea value={managerNote} onChange={(event) => setManagerNote(event.target.value)} /></label>
                <div className="actions">
                  <button type="button" disabled={isSubmitting || !preview || selected.status === "closed"} onClick={() => void closePeriod()}>close</button>
                  <button type="button" disabled={isSubmitting || selected.status !== "closed"} onClick={() => void periodAction("reopen")}>reopen</button>
                  <button type="button" disabled={isSubmitting || selected.status === "closed" || selected.status === "archived"} onClick={() => void periodAction("archive")}>archive</button>
                </div>
              </section>
            ) : <p className="subtle-text">閲覧のみです。</p>}
          </aside>
        ) : null}
      </div>
      {preview ? (
        <section className="inline-alert">
          <h3>preview</h3>
          <dl>
            <dt>対象</dt><dd>{preview.summary.date_from} - {preview.summary.date_to}</dd>
            <dt>件数</dt><dd>{preview.summary.snapshot_count}件 / staff {preview.summary.staff_count}</dd>
            <dt>warning/error</dt><dd>{preview.summary.warning_count} / {preview.summary.error_count}</dd>
            <dt>勤務分</dt><dd>{preview.summary.worked_minutes}分</dd>
          </dl>
          {issueItems.length ? (
            <table className="table">
              <thead><tr><th>勤務日</th><th>スタッフ</th><th>warning/error</th><th>予定</th><th>勤務分</th></tr></thead>
              <tbody>
                {issueItems.slice(0, 80).map((item) => (
                  <tr key={`${item.staff}-${item.work_date}-${item.attendance_record ?? "scheduled"}`}>
                    <td>{item.work_date}</td>
                    <td>{item.employee_code} {item.staff_display_name}</td>
                    <td>{item.issues.map((issue) => `${issue.severity}:${issue.code}`).join(" / ")}</td>
                    <td>{offsetRange(item)}</td>
                    <td>{item.worked_minutes}分</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="subtle-text">warning/errorはありません。</p>}
          <h3>staff summaries</h3>
          <table className="table">
            <thead><tr><th>スタッフ</th><th>予定日</th><th>実績日</th><th>勤務分</th><th>warning</th><th>未確定</th></tr></thead>
            <tbody>
              {preview.staff_summaries.map((summary) => (
                <tr key={summary.staff}>
                  <td>{summary.employee_code_snapshot} {summary.staff_display_name_snapshot}</td>
                  <td>{summary.scheduled_days}</td>
                  <td>{summary.worked_days}</td>
                  <td>{summary.worked_minutes}</td>
                  <td>{summary.warning_count}</td>
                  <td>{summary.unconfirmed_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </section>
  );
}
