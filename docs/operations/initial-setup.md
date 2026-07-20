# 初期導入手順

本番導入は承認済みのHTTPS環境とPostgreSQLを前提にします。secret、DB password、実在ユーザー情報をリポジトリやcontainer imageへ含めません。

## 1. 環境変数

`.env.example`を基に、secret管理基盤へ`DJANGO_SECRET_KEY`、`DJANGO_DEBUG=0`、`DJANGO_ENVIRONMENT=production`、`DATABASE_URL`またはPostgreSQL個別設定、許可host、CSRF origin、frontend origin、SSL・cookie・HSTS・proxy設定、`LOG_LEVEL`を登録します。HSTS preloadは対象domainの全subdomainがHTTPS対応済みか確認してから有効化します。

## 2. DB作成

UTF-8の専用PostgreSQL DBと最小権限のapplication userを作成します。管理者資格情報をapplicationへ渡しません。接続暗号化、backup、容量監視を構成します。

## 3. migrate

対象image/tagを固定し、`python manage.py migrate --plan`を確認後、保守時間内に`python manage.py migrate --noinput`を実行します。失敗時は処理を止め、途中状態を確認します。

## 4. superuser作成

```bash
python manage.py createsuperuser
```

個人ごとの管理者accountを作成し、共有accountを避けます。初回passwordを安全な経路で設定し、不要なDjango superuser権限を常用しません。

## 5. Location作成

system adminでloginし、拠点code、名称、timezone、active状態を登録します。codeと年月の運用単位を確定します。

## 6. WorkArea等マスタ作成

WorkArea、WorkCategory、WorkTypeと必要な利用可能関係を登録します。無効化運用と表示順を確認します。

## 7. staff登録

employee code、氏名、role、初期password状態を登録します。退職・停止時はhard deleteせずdeactivateします。

## 8. StaffLocation

スタッフごとに所属拠点と有効期間を設定し、重複・期間切れがないことを確認します。

## 9. StaffCapability

担当可能なWorkType、level、有効期間を登録します。dated shiftで不足がerror/warningになることを試験します。

## 10. ShiftPattern

15分単位、翌日を含む0から2880分の規則でpatternとsegmentを作成します。休憩と業務segmentを区別します。

## 11. WeeklyTemplate

曜日、staff、patternの割当を作成し、月間生成previewで配属・能力・希望のwarningを確認します。

## 12. 単価・手当

`system_admin`または`shift_manager`で、適用期間を重複させず勤務単価・手当を設定します。正式給与値ではなく概算人件費設定であることを運用担当者へ周知します。

## 13. 売上区分

拠点ごとに英数字・hyphen・underscoreのcodeで売上区分を登録します。過去snapshotを守るため、使用済み区分は削除せず無効化します。

## 14. 権限確認

`system_admin`、`shift_manager`、`supervisor`、`staff`、`viewer`のtest accountでメニューと主要APIを確認します。特に単価・人件費・売上・人件費率は前二roleだけに表示されること、staffは本人データだけ取得できることを確認します。

## 15. health/readiness

```bash
python manage.py check --deploy
python manage.py check_deployment_readiness
curl --fail https://manager.example.jp/api/v1/health/
curl --fail https://manager.example.jp/api/v1/readiness/
```

レスポンスが最小情報だけで、readinessが`ready`になることを確認します。

## 16. 初回バックアップ

[バックアップ・復元手順](backup-and-restore.md)に従って初回dump、checksum、media対応表を保存し、隔離環境へ復元して検証します。

## 17. 運用開始前チェック

[リリースチェックリスト](release-checklist.md)を完了し、管理者連絡網、日次/月次担当、障害時責任者、保守時間、rollback基準を合意します。ステージングでlogin、シフト、勤怠、月次締め、概算人件費、予算、売上finalize、CSVのsmoke testを終えてから利用開始します。
