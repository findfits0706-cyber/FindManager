# 本番リリースチェックリスト

対象version、commit SHA、実施者、承認者、予定時刻、rollback責任者を作業記録へ記載します。未実行項目を成功扱いにしません。

## Sourceと変更範囲

- [ ] `main`がoriginの最新commitで、対象branchのbaseを確認した
- [ ] release対象commit SHAと`1.0.0-rc1`のrelease noteが一致する
- [ ] working treeがcleanで、未追跡file・stash・未push commitがない
- [ ] `git diff --check`が成功する
- [ ] migration fileがmodel変更と同じcommitに含まれる
- [ ] `makemigrations --check`で未生成migrationがない
- [ ] `showmigrations`と`migrate --plan`を確認した
- [ ] rollback対象の直前image/tagとDB互換性を確認した

## Backend

- [ ] `ruff check .`が成功する
- [ ] `ruff format --check .`が成功する
- [ ] 全Backend `pytest`が成功する
- [ ] PostgreSQL serviceを使用した主要testが成功する
- [ ] `python manage.py check`が成功する
- [ ] 本番相当環境変数で`python manage.py check --deploy`が成功する
- [ ] `python manage.py check_deployment_readiness`がerrorなしで成功する
- [ ] Python依存の既知脆弱性監査にblockerがない

## FrontendとE2E

- [ ] `npm ci`がlockfileどおり成功する
- [ ] `npm run lint`が成功する
- [ ] `npm run typecheck`が成功する
- [ ] 全Frontend unit testが成功する
- [ ] `npm run build`が`VITE_APP_VERSION`を指定して成功する
- [ ] `npm audit --audit-level=low`に未対応findingがない
- [ ] Playwright主要E2Eが専用DBで成功する
- [ ] E2E失敗時のtrace、screenshot、log artifactを取得できる
- [ ] form label、button name、focus、table header、loading、disabled、empty/error stateを確認した

## Securityと権限

- [ ] `DJANGO_DEBUG=0`である
- [ ] `DJANGO_SECRET_KEY`が強い本番secretとして外部管理され、imageやlogに含まれない
- [ ] `DJANGO_ALLOWED_HOSTS`に必要hostだけを設定し、wildcardがない
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS`と`FRONTEND_ORIGIN`がHTTPSの正しいoriginである
- [ ] `SESSION_COOKIE_SECURE`と`CSRF_COOKIE_SECURE`が有効である
- [ ] `SECURE_SSL_REDIRECT`とproxy SSL headerを実構成で検証した
- [ ] HSTSの期間、subdomain、preloadをdomain運用者が承認した
- [ ] password、session、CSRF、Authorization、secret、個人単価・人件費、売上明細がlogへ出ない
- [ ] role matrixが全roleとanonymousで成功する
- [ ] staff本人scope、UUID直接指定、query parameterによる越権を検証した
- [ ] supervisor/staff/viewerへ単価・手当・人件費・売上・人件費率が漏れない
- [ ] 管理者account、MFA等の外部認証方針、初期password変更状態を確認した

## Infrastructureと回復

- [ ] Backend/Frontend container imageがbuildでき、non-rootで起動する
- [ ] PostgreSQL、migration、healthcheck、環境変数、volume設計を確認した
- [ ] `/api/v1/health/`が`ok`を返す
- [ ] `/api/v1/readiness/`が`ready`を返す
- [ ] `/system/status`がsystem adminだけに安全な要約を返す
- [ ] 構造化logを収集でき、request IDで相関できる
- [ ] リリース直前backup、checksum、media、image/tagを保存した
- [ ] 本番同等の隔離環境でrestore rehearsalを完了した
- [ ] backup保持期間、暗号化、access control、削除手順を確認した
- [ ] DB障害、migration失敗、500増加、情報漏えい疑いの連絡網を確認した

## 業務smoke test

- [ ] login、logout、session切れ、403、404、通信error表示を確認した
- [ ] 拠点・staff・業務masterの参照と権限を確認した
- [ ] 月間シフト作成、assignment、confirm、publish、本人閲覧を確認した
- [ ] 希望提出、変更申請、manager review/apply、再公開を確認した
- [ ] clock in、break、clock out、修正、confirmを確認した
- [ ] 勤怠closing preview、acknowledgement、close、閉鎖後拒否を確認した
- [ ] 単価・手当、概算人件費preview/finalizeを確認した
- [ ] 人件費予算preview/approve/varianceを確認した
- [ ] 売上区分、売上予算approve、実績finalize、performanceを確認した
- [ ] UTF-8 BOM CSVを権限のある端末で開き、日本語と金額を確認した

## Releaseと完了

- [ ] GitHub ActionsのBackend、Frontend、E2E、Dockerがgreenである
- [ ] downtime、migration、smoke test、監視強化時間を利用者へ周知した
- [ ] rollback plan、判断基準、責任者、復旧目標を承認した
- [ ] release tagを対象commitへ付与する準備ができた
- [ ] release notes、既知の制約、未実装範囲を承認した
- [ ] deploy後smoke testと監視で異常がない
- [ ] 作業記録に結果、時刻、request ID、backup ID、承認を残した
