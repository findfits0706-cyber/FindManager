import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { SystemStatus } from "../lib/types";

const frontendVersion = import.meta.env.VITE_APP_VERSION ?? "1.0.0-rc1";

function statusLabel(value: string) {
  const labels: Record<string, string> = {
    ok: "正常",
    ready: "準備完了",
    not_ready: "要確認",
    up_to_date: "適用済み",
    pending: "未適用あり",
    connected: "接続済み",
    unavailable: "利用不可",
    development: "開発",
    test: "テスト",
    production: "本番",
  };
  return labels[value] ?? value;
}

function dateTime(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "medium" }).format(new Date(value))
    : "なし";
}

export function SystemStatusPage() {
  const { user, loading } = useAuth();
  const isSystemAdmin = user?.roles.includes("system_admin") ?? false;
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api<SystemStatus>("/api/v1/system/status/"),
    enabled: isSystemAdmin,
    retry: false,
  });

  if (loading) return <p role="status">権限を確認しています。</p>;
  if (!isSystemAdmin) return <Navigate to="/403" replace />;

  const error = query.error instanceof ApiError ? query.error : null;
  return (
    <section className="system-status-page" aria-labelledby="system-status-title">
      <div className="page-header compact-header">
        <div>
          <p className="eyebrow">System Administration</p>
          <h2 id="system-status-title">システム状態</h2>
        </div>
        <button type="button" onClick={() => void query.refetch()} disabled={query.isFetching}>
          {query.isFetching ? "更新中" : "更新"}
        </button>
      </div>

      {query.isLoading && <p role="status">システム状態を確認しています。</p>}
      {query.isError && (
        <div className="error-banner" role="alert">
          <p>システム状態を取得できませんでした。</p>
          {error?.requestId && <p className="request-id">Request ID: {error.requestId}</p>}
        </div>
      )}
      {query.data && (
        <>
          <div className="status-summary" aria-label="稼働状態">
            <div><span>API</span><strong>{statusLabel(query.data.api_health)}</strong></div>
            <div><span>Readiness</span><strong>{statusLabel(query.data.api_readiness)}</strong></div>
            <div><span>Database</span><strong>{statusLabel(query.data.database_status)}</strong></div>
            <div><span>Migration</span><strong>{statusLabel(query.data.migration_status)}</strong></div>
          </div>

          <div className="table-wrap">
            <table>
              <caption>バージョンと環境</caption>
              <tbody>
                <tr><th scope="row">Frontend build</th><td>{frontendVersion}</td></tr>
                <tr><th scope="row">Backend</th><td>{query.data.backend_version}</td></tr>
                <tr><th scope="row">Environment</th><td>{statusLabel(query.data.environment)}</td></tr>
                <tr><th scope="row">最終監査イベント</th><td>{dateTime(query.data.last_audit_event_at)}</td></tr>
              </tbody>
            </table>
          </div>

          <div className="table-wrap">
            <table>
              <caption>運用集計</caption>
              <tbody>
                <tr><th scope="row">稼働中拠点</th><td>{query.data.active_location_count}</td></tr>
                <tr><th scope="row">有効スタッフ</th><td>{query.data.active_staff_count}</td></tr>
                <tr><th scope="row">未処理申請</th><td>{query.data.pending_request_count}</td></tr>
                <tr><th scope="row">未締め勤怠期間</th><td>{query.data.unclosed_attendance_period_count}</td></tr>
                <tr><th scope="row">未確定概算人件費</th><td>{query.data.unfinalized_labor_estimate_period_count}</td></tr>
                <tr><th scope="row">未承認人件費予算</th><td>{query.data.unapproved_labor_budget_period_count}</td></tr>
                <tr><th scope="row">未確定売上実績</th><td>{query.data.unfinalized_revenue_actual_period_count}</td></tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
