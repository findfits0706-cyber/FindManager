import { useEffect, useState } from "react";
import { API_ERROR_EVENT, SESSION_EXPIRED_EVENT, type ApiErrorDetail } from "../api/client";

type Notice = ApiErrorDetail & { sessionExpired: boolean };

export function GlobalErrorNotice() {
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    const apiError = (event: Event) => {
      setNotice({ ...(event as CustomEvent<ApiErrorDetail>).detail, sessionExpired: false });
    };
    const sessionExpired = (event: Event) => {
      setNotice({ ...(event as CustomEvent<ApiErrorDetail>).detail, sessionExpired: true });
    };
    window.addEventListener(API_ERROR_EVENT, apiError);
    window.addEventListener(SESSION_EXPIRED_EVENT, sessionExpired);
    return () => {
      window.removeEventListener(API_ERROR_EVENT, apiError);
      window.removeEventListener(SESSION_EXPIRED_EVENT, sessionExpired);
    };
  }, []);

  if (!notice) return null;
  return (
    <div className="global-error-notice" role="alert" aria-live="assertive">
      <div>
        <strong>{notice.sessionExpired ? "セッションの有効期限が切れました" : "通信エラー"}</strong>
        <p>{notice.sessionExpired ? "再度ログインしてください。" : notice.message}</p>
        {notice.requestId && <p className="request-id">Request ID: {notice.requestId}</p>}
      </div>
      <div className="notice-actions">
        {!notice.sessionExpired && (
          <button type="button" onClick={() => window.location.reload()}>
            再読み込み
          </button>
        )}
        <button type="button" className="secondary" onClick={() => setNotice(null)} aria-label="通知を閉じる">
          閉じる
        </button>
      </div>
    </div>
  );
}
