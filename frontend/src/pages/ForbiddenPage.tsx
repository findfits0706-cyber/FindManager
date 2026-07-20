import { Link } from "react-router-dom";

export function ForbiddenPage() {
  return (
    <section className="http-error-page" aria-labelledby="forbidden-title">
      <p className="status-code">403</p>
      <h2 id="forbidden-title">このページを表示する権限がありません</h2>
      <p>必要な権限が付与されているか、管理者へ確認してください。</p>
      <Link to="/">ホームへ戻る</Link>
    </section>
  );
}
