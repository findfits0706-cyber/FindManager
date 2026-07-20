# 障害対応手順

## 共通初動

1. 発生時刻、環境、利用者、URL、HTTP status、画面のrequest ID、直前操作を記録する。
2. 影響範囲と継続可否を判断し、必要なら書き込み停止・メンテナンス表示へ切り替える。
3. 構造化ログ、監査event、health/readiness、直近deploy・migrationを確認する。password、cookie、token、財務明細をticketやchatへ貼らない。
4. DB直接更新、log削除、無計画なrollbackを避け、責任者と復旧方針を合意する。
5. 復旧後に原因、影響データ、対応、再発防止、検証結果を記録する。

## login不可

- health/readiness、CSRF origin、secure cookie、HTTPS、時刻、account active状態、初回password変更状態、429 throttleを確認する。
- 特定userだけなら無効化・role・sessionを確認し、承認済みのpassword resetを行う。
- 全員なら設定・proxy・cookie domain・DBを調査する。秘密値をlog出力して確認しない。

## DB接続不可

- readinessをtrafficから外し、DB service、DNS、TLS、接続上限、容量、資格情報の登録状態を確認する。
- applicationを連続restartして負荷を増やさない。DB復旧後にmigrationと`check_deployment_readiness`を実行する。
- データ破損が疑われる場合は[バックアップ・復元手順](backup-and-restore.md)へ進む。

## migration失敗

- 新規書き込みを停止し、失敗したmigration、DB transaction状態、適用済み一覧、deploy imageを固定する。
- `showmigrations`と`migrate --plan`を確認する。安易なfake適用やmigration file変更を行わない。
- forward fixかリリース前DB復元かをmigrationの可逆性とデータ変更から判断する。

## 500増加

- request IDで同一例外を集約し、status、path、exception type、直近releaseとの相関を見る。
- 秘密・個人・財務情報を追加logへ出さず再現する。影響機能を停止または直前imageへrollbackする。
- stack traceはserver側だけで扱い、利用者にはrequest IDと代替手順を案内する。

## 誤った月次締め

- 対象拠点・年月、closing ID、誤り、後続処理の有無を記録する。
- 概算人件費以降が未確定であることを確認してattendance closingをreopenし、修正、再preview、fingerprint確認、closeを行う。
- 後続finalize済みなら、逆順に影響を確認し、責任者承認の下で各workflowをreopenする。

## 誤った概算確定

- 売上実績finalizeや予実報告への利用状況を確認する。
- labor estimateをreopenし、単価・手当・勤怠sourceを修正、再preview、再finalizeする。関連する人件費予算varianceと売上performanceも再確認する。

## 誤った予算承認

- approved人件費予算または売上予算を直接編集・archiveしない。
- 関連する実績finalize前にreopenし、修正、preview、再approveする。既に実績snapshotへ使用済みなら影響範囲と再finalize方針を承認してから進める。

## 誤った売上finalize

- revenue actual periodとperformance snapshot、出力済みCSV、閲覧者を特定する。
- periodをreopenし、売上lineまたはsource periodを修正、最新previewとfingerprintで再finalizeする。古いCSVを回収し、差し替えを明示する。

## バックアップ復元

- 復旧時点と許容データ損失を責任者が決定する。
- 書き込み停止、現状退避、checksum確認、隔離DB復元、migration・readiness・snapshot・権限・smoke testの順で検証する。
- 検証を省略して本番接続先を切り替えない。

## 個人情報漏えい疑い

- 影響経路を遮断し、証拠を保全する。関連account/session/tokenを失効させるが、監査logを削除しない。
- 対象情報、対象者、期間、閲覧・出力経路を最小権限で特定する。
- 組織の個人情報・法務・経営エスカレーション手順に従い、通知要否を判断する。
- 原因修正後にrole matrix、object permission、serializer、frontend表示、log allowlistを再検証する。
