import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Paginated, ShiftRequestPeriod, ShiftRequestSubmission } from "../lib/types";

function formatLocalDateTimeInput(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

const initialForm = () => {
  const opensAt = new Date();
  const closesAt = new Date(opensAt.getTime() + 7 * 24 * 60 * 60 * 1000);
  return {
    name: "",
    description: "",
    opens_at: formatLocalDateTimeInput(opensAt),
    closes_at: formatLocalDateTimeInput(closesAt),
  };
};

export function ShiftRequestPeriodsPage() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const [location, setLocation] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [form, setForm] = useState(initialForm);
  const [editingPeriod, setEditingPeriod] = useState<ShiftRequestPeriod | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<ShiftRequestPeriod | null>(null);
  const [selectedSubmission, setSelectedSubmission] = useState<ShiftRequestSubmission | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const locationQuery = useQuery({
    queryKey: ["locations", "shift-request-periods"],
    queryFn: () => api<Paginated<{ id: string; name: string }>>("/api/v1/locations/?page_size=100&is_active=true"),
  });
  const periodQuery = useQuery({
    queryKey: ["shift-request-periods", location, year, month],
    queryFn: () =>
      api<Paginated<ShiftRequestPeriod>>(
        `/api/v1/shift-request-periods/?page_size=100&year=${year}&month=${month}${location ? `&location=${location}` : ""}`,
      ),
  });
  const submissionsQuery = useQuery({
    enabled: Boolean(selectedPeriod),
    queryKey: ["shift-request-period-submissions", selectedPeriod?.id],
    queryFn: () => api<ShiftRequestSubmission[]>(`/api/v1/shift-request-periods/${selectedPeriod?.id}/submissions/`),
  });

  const resetForm = () => {
    setEditingPeriod(null);
    setForm(initialForm());
  };

  const createPeriod = async () => {
    if (!location || !canManage) return;
    setError("");
    setMessage("");
    try {
      await api("/api/v1/shift-request-periods/", {
        method: "POST",
        body: JSON.stringify({
          location,
          year,
          month,
          name: form.name || `${year}年${month}月 希望提出`,
          description: form.description,
          opens_at: form.opens_at,
          closes_at: form.closes_at,
        }),
      });
      setMessage("希望提出期間を作成しました。");
      resetForm();
      await periodQuery.refetch();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "希望提出期間の作成に失敗しました。");
    }
  };

  const startEdit = (period: ShiftRequestPeriod) => {
    setEditingPeriod(period);
    setForm({
      name: period.name,
      description: period.description,
      opens_at: period.opens_at.slice(0, 16),
      closes_at: period.closes_at.slice(0, 16),
    });
  };

  const updatePeriod = async () => {
    if (!editingPeriod || !canManage) return;
    setError("");
    setMessage("");
    try {
      const updated = await api<ShiftRequestPeriod>(`/api/v1/shift-request-periods/${editingPeriod.id}/`, {
        method: "PATCH",
        body: JSON.stringify(form),
      });
      setMessage("希望提出期間を更新しました。");
      setEditingPeriod(null);
      setForm(initialForm());
      if (selectedPeriod?.id === updated.id) {
        setSelectedPeriod(updated);
      }
      await periodQuery.refetch();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "希望提出期間の更新に失敗しました。");
    }
  };

  const periodAction = async (period: ShiftRequestPeriod, action: "open" | "close" | "reopen" | "archive") => {
    if (!canManage) return;
    setError("");
    setMessage("");
    try {
      await api(`/api/v1/shift-request-periods/${period.id}/${action}/`, { method: "POST", body: JSON.stringify({}) });
      setMessage(`Periodを${action}しました。`);
      await periodQuery.refetch();
      if (selectedPeriod?.id === period.id) {
        const updated = await api<ShiftRequestPeriod>(`/api/v1/shift-request-periods/${period.id}/`);
        setSelectedPeriod(updated);
      }
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "状態変更に失敗しました。");
    }
  };

  const submissionAction = async (submission: ShiftRequestSubmission, action: "return" | "lock" | "unlock") => {
    if (!canManage) return;
    const reason = action === "return" ? window.prompt("差戻し理由を入力してください。") : "";
    if (action === "return" && !reason) return;
    setError("");
    setMessage("");
    try {
      await api(`/api/v1/shift-request-submissions/${submission.id}/${action}/`, {
        method: "POST",
        body: JSON.stringify(action === "return" ? { reason } : {}),
      });
      setMessage(`Submissionを${action}しました。`);
      await submissionsQuery.refetch();
      await periodQuery.refetch();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "提出状態の変更に失敗しました。");
    }
  };

  return (
    <section className="card monthly-page">
      <div className="section-header"><div><p className="eyebrow">Shift requests</p><h2>希望提出管理</h2></div></div>
      <div className="toolbar field-grid">
        <label>拠点<select value={location} onChange={(event) => setLocation(event.target.value)}><option value="">すべて</option>{locationQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>年<input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} /></label>
      </div>
      {canManage ? <div className="toolbar field-grid">
        <label>name<input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /></label>
        <label>description<input value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} /></label>
        <label>opens_at<input type="datetime-local" value={form.opens_at} onChange={(event) => setForm((current) => ({ ...current, opens_at: event.target.value }))} /></label>
        <label>closes_at<input type="datetime-local" value={form.closes_at} onChange={(event) => setForm((current) => ({ ...current, closes_at: event.target.value }))} /></label>
        {editingPeriod ? <button type="button" onClick={() => void updatePeriod()}>編集保存</button> : <button type="button" onClick={() => void createPeriod()}>作成</button>}
        {editingPeriod ? <button type="button" onClick={resetForm}>編集取消</button> : null}
      </div> : null}
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {periodQuery.isLoading ? <p>読み込み中...</p> : null}
      {periodQuery.isError ? <p className="error">希望提出期間の取得に失敗しました。</p> : null}
      {!periodQuery.isLoading && !periodQuery.isError && periodQuery.data?.results.length === 0 ? <p className="subtle-text">希望提出期間はありません。</p> : null}
      <table className="table">
        <thead><tr><th>拠点</th><th>年月</th><th>status</th><th>開始</th><th>締切</th><th>提出状況</th><th></th></tr></thead>
        <tbody>{periodQuery.data?.results.map((period) => (
          <tr key={period.id}>
            <td>{period.location_name}</td><td>{period.year}/{period.month}</td><td>{period.status}</td><td>{period.opens_at}</td><td>{period.closes_at}</td>
            <td>対象 {period.target_staff_count ?? 0} / draft {period.draft_count ?? 0} / submitted {period.submitted_count ?? 0} / returned {period.returned_count ?? 0} / locked {period.locked_count ?? 0} / 未作成 {period.not_created_count ?? 0} / item {period.item_count ?? 0}</td>
            <td><button type="button" onClick={() => setSelectedPeriod(period)}>提出状況</button>{canManage ? <><button type="button" onClick={() => startEdit(period)}>編集</button><button type="button" onClick={() => void periodAction(period, "open")}>open</button><button type="button" onClick={() => void periodAction(period, "close")}>close</button><button type="button" onClick={() => void periodAction(period, "reopen")}>reopen</button><button type="button" onClick={() => void periodAction(period, "archive")}>archive</button></> : null}</td>
          </tr>
        ))}</tbody>
      </table>
      {selectedPeriod ? <section className="preview-panel"><h3>提出状況 {selectedPeriod.name}</h3>
        {submissionsQuery.isLoading ? <p>読み込み中...</p> : null}
        {submissionsQuery.isError ? <p className="error">提出状況の取得に失敗しました。</p> : null}
        <table className="table"><thead><tr><th>スタッフ</th><th>status</th><th>提出日時</th><th>差戻し理由</th><th>希望件数</th><th></th></tr></thead><tbody>{submissionsQuery.data?.map((submission) => <tr key={submission.id}><td>{submission.staff_display_name}</td><td>{submission.status}</td><td>{submission.submitted_at ?? ""}</td><td>{submission.return_reason}</td><td>{submission.item_count ?? submission.items.length}</td><td><button type="button" onClick={() => setSelectedSubmission(submission)}>詳細</button>{canManage ? <><button type="button" onClick={() => void submissionAction(submission, "return")}>return</button><button type="button" onClick={() => void submissionAction(submission, "lock")}>lock</button><button type="button" onClick={() => void submissionAction(submission, "unlock")}>unlock</button></> : null}</td></tr>)}</tbody></table>
      </section> : null}
      {selectedSubmission ? <section className="preview-panel"><h3>{selectedSubmission.staff_display_name}</h3><p>{selectedSubmission.notes}</p><table className="table"><thead><tr><th>種別</th><th>日付</th><th>時間</th><th>理由</th><th>備考</th></tr></thead><tbody>{selectedSubmission.items.map((item) => <tr key={item.id}><td>{item.request_type}</td><td>{item.work_date}</td><td>{item.start_offset_minutes ?? ""}~{item.end_offset_minutes ?? ""}</td><td>{item.reason}</td><td>{item.notes}</td></tr>)}</tbody></table></section> : null}
    </section>
  );
}
