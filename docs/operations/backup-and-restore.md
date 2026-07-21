# バックアップ・復元手順

## 適用範囲

本書はPostgreSQLを使用する本番・ステージング環境と、SQLiteを使用するローカル開発環境を対象とします。例の接続名・パスは仮値です。本番秘密値や実データをリポジトリへ保存しないでください。

## PostgreSQLバックアップ

### 事前確認

1. 対象環境、DB名、リリースversion、適用migrationを記録する。
2. DB容量、保存先空き容量、`pg_dump`とサーバーのmajor version互換性を確認する。
3. 月次締めやfinalizeなど長いtransactionがない時間帯を選ぶ。
4. 保存先が暗号化され、アクセス権と監査が設定されていることを確認する。

DBを停止せず整合した論理バックアップを取得できます。資格情報は`.pgpass`や承認済みsecret管理から渡し、コマンド履歴へpasswordを書きません。

```bash
pg_dump --format=custom --no-owner --no-acl --file=findmanager_YYYYMMDD_HHMM.dump findmanager
pg_restore --list findmanager_YYYYMMDD_HHMM.dump > findmanager_YYYYMMDD_HHMM.list
sha256sum findmanager_YYYYMMDD_HHMM.dump > findmanager_YYYYMMDD_HHMM.dump.sha256
```

取得後、終了code、ファイルsize、一覧、checksumを確認します。各バックアップは上書きせず、日次・月次・リリース前などの分類を付けます。

### mediaとstatic

- ユーザーが登録した`MEDIA_ROOT`はDBと同じ復旧時点になるよう別途バックアップする。
- `STATIC_ROOT`はbuild成果物から再生成できるため原則バックアップ不要。デプロイimageまたはcommit/tagを保存する。
- DB、media、リリースimageの対応関係をバックアップ台帳に記録する。

### 暗号化・保存期間

- 転送時と保管時を暗号化し、復号鍵はバックアップ本体と分離する。
- 最小権限、MFA、アクセスログ、改ざん防止または世代管理を有効にする。
- 保存期間は組織規程と個人情報ポリシーで決定する。例として日次35日、月次13か月、リリース前バックアップをリリース存続期間中保持する。
- 期限切れ削除も監査可能にし、単一の保存先・単一世代へ依存しない。

## PostgreSQL復元

復元はまず隔離した検証DBでリハーサルします。対象DBの置換は破壊的操作なので、責任者承認と復旧時点の合意なしに実行しません。

1. 障害範囲、復旧時点、使用するdump/checksum、対応image/tagを決定する。
2. 書き込みと定期jobを停止し、メンテナンス表示へ切り替える。
3. 現在DBも可能なら退避し、証跡を保存する。
4. dumpのchecksumと`pg_restore --list`を確認する。
5. 空の復元先DBを作成し、dumpを復元する。

```bash
createdb findmanager_restore
pg_restore --exit-on-error --clean --if-exists --no-owner --no-acl --dbname=findmanager_restore findmanager_YYYYMMDD_HHMM.dump
```

6. バックアップ時のmigrationと実行imageを照合し、先に`migrate --plan`で差分を確認する。
7. 必要な前進migrationだけを適用する。古いコードと新しいschemaを混在させない。
8. 対応するmediaを復元し、staticは同じrelease imageから再配布する。
9. 以下を実行し、errorがないことを確認する。

```bash
python manage.py showmigrations
python manage.py check
python manage.py check_deployment_readiness
```

10. health、readiness、login、権限、シフト閲覧、勤怠、最新月次snapshot、CSVを検証する。
11. 件数・最新監査日時・承認/finalize状態を復元前台帳と照合する。
12. 責任者承認後に接続先を切り替え、書き込みを再開し、ログと主要機能を監視する。

本番復元の成否は`pg_restore`の終了だけで判断せず、migration、snapshot整合性、権限、アプリsmoke testまで確認します。

## SQLite開発環境

Djangoと開発serverを停止し、WALが残っていないことを確認してからDBファイルをcopyします。稼働中の単純copyは使用しません。

```powershell
Copy-Item -LiteralPath backend\db.sqlite3 -Destination backups\db-YYYYMMDD-HHMM.sqlite3
Get-FileHash backups\db-YYYYMMDD-HHMM.sqlite3 -Algorithm SHA256
```

より安全に取得する場合はSQLite CLIの`.backup`を使用します。復元は元ファイルを退避してcopyを戻し、`python manage.py check`、`showmigrations`、loginと主要画面を確認します。SQLiteバックアップは開発用途に限定し、本番PostgreSQLの代替にしません。
