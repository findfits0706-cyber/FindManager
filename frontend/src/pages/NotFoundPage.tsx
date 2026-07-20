import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="http-error-page" aria-labelledby="not-found-title">
      <p className="status-code">404</p>
      <h1 id="not-found-title">ページが見つかりません</h1>
      <p>URLを確認するか、ホームから操作をやり直してください。</p>
      <Link to="/">ホームへ戻る</Link>
    </main>
  );
}
