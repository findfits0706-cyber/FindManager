import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Paginated, ShiftRequestPeriod, ShiftRequestSubmission } from "../lib/types";

const nowIso = () => new Date().toISOString();

export function ShiftRequestPeriodsPage() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const [location, setLocation] = useState("");
  const [year, setYear] = useState(new Date().getFullYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [selectedPeriod, setSelectedPeriod] = useState<ShiftRequestPeriod | null>(null);
  const [selectedSubmission, setSelectedSubmission] = useState<ShiftRequestSubmission | null>(null);
  const [error, setError] = useState("");
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

  const createPeriod = async () => {
    if (!location || !canManage) return;
    setError("");
    try {
      await api("/api/v1/shift-request-periods/", {
        method: "POST",
        body: JSON.stringify({
          location,
          year,
          month,
          name: `${year}年${month}月 希望提出`,
          description: "",
          opens_at: nowIso(),
          closes_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
        }),
      });
      await periodQuery.refetch();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "希望提出期間の作成に失敗しました。");
    }
  };

  const periodAction = async (period: ShiftRequestPeriod, action: "open" | "close" | "reopen" | "archive") => {
    if (!canManage) return;
    await api(`/api/v1/shift-request-periods/${period.id}/${action}/`, { method: "POST", body: JSON.stringify({}) });
    await periodQuery.refetch();
    if (selectedPeriod?.id === period.id) {
      const updated = await api<ShiftRequestPeriod>(`/api/v1/shift-request-periods/${period.id}/`);
      setSelectedPeriod(updated);
    }
  };

  const submissionAction = async (submission: ShiftRequestSubmission, action: "return" | "lock" | "unlock") => {
    if (!canManage) return;
    const reason = action === "return" ? window.prompt("差戻し理由を入力してください。") : "";
    if (action === "return" && !reason) return;
    await api(`/api/v1/shift-request-submissions/${submission.id}/${action}/`, {
      method: "POST",
      body: JSON.stringify(action === "return" ? { reason } : {}),
    });
    await submissionsQuery.refetch();
  };

  return (
    <section className="card monthly-page">
      <div className="section-header"><div><p className="eyebrow">Shift requests</p><h2>希望提出管理</h2></div></div>
      <div className="toolbar field-grid">
        <label>拠点<select value={location} onChange={(event) => setLocation(event.target.value)}><option value="">すべて</option>{locationQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>年<input type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => setMonth(Number(event.target.value))} /></label>
        {canManage ? <button type="button" onClick={() => void createPeriod()}>作成</button> : null}
      </div>
      {error ? <p className="error">{error}</p> : null}
      {periodQuery.isLoading ? <p>読み込み中...</p> : null}
      {periodQuery.isError ? <p className="error">希望提出期間の取得に失敗しました。</p> : null}
      {!periodQuery.isLoading && !periodQuery.isError && periodQuery.data?.results.length === 0 ? <p className="subtle-text">希望提出期間はありません。</p> : null}
      <table className="table">
        <thead><tr><th>拠点</th><th>年月</th><th>status</th><th>開始</th><th>締切</th><th>提出状況</th><th></th></tr></thead>
        <tbody>{periodQuery.data?.results.map((period) => (
          <tr key={period.id}>
            <td>{period.location_name}</td><td>{period.year}/{period.month}</td><td>{period.status}</td><td>{period.opens_at}</td><td>{period.closes_at}</td>
            <td>draft {period.draft_count ?? 0} / submitted {period.submitted_count ?? 0} / returned {period.returned_count ?? 0} / locked {period.locked_count ?? 0}</td>
            <td><button type="button" onClick={() => setSelectedPeriod(period)}>提出状況</button>{canManage ? <><button type="button" onClick={() => void periodAction(period, "open")}>open</button><button type="button" onClick={() => void periodAction(period, "close")}>close</button><button type="button" onClick={() => void periodAction(period, "reopen")}>reopen</button><button type="button" onClick={() => void periodAction(period, "archive")}>archive</button></> : null}</td>
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
