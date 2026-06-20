# FindManager

ファインドスポーツクラブ運営管理システムの工程1実装です。対象はプロジェクト基盤、認証、スタッフ、権限です。

## 必要環境
- Python 3.13 以上
- Node.js 24 系
- npm
- Docker Compose

## 初期セットアップ
1. `.env.example` を `.env` にコピー
2. `backend` で依存関係をインストール
3. `frontend` で `npm install`
4. `python manage.py migrate`
5. `python manage.py seed_dev`

`seed_dev` は `DEV_SEED_PASSWORD` を参照します。`.env` に `DEV_SEED_PASSWORD=任意の開発用パスワード` を設定すると、その値で開発ユーザーを投入できます。

## Windows での起動方法
- `scripts/bootstrap.ps1`
- `backend` で `python manage.py runserver`
- `frontend` で `npm run dev`

## Docker Compose 起動方法
- `docker compose up --build`

## 開発用ユーザー
- `DEV_SEED_PASSWORD` を設定している場合はその値が使用されます
- 未設定時は開発専用の既定パスワード `DevPassword123!` が使用され、コマンド実行時に警告が表示されます
- `system_admin`
- `shift_manager`
- `supervisor`
- `staff`
- `viewer`

## DB 方針
- SQLite は簡易ローカル開発専用です
- 正式な開発確認、CI、本番は PostgreSQL を使用します
- 予約競合、排他制御、制約の正式検証は PostgreSQL で行います
- SQLite のみでテスト成功しても完了条件とはしません

## テスト方法
- Backend:
  - `ruff check .`
  - `ruff format --check .`
  - `pytest`
  - `python manage.py makemigrations --check`
  - `python manage.py check`
- Frontend:
  - `npm run lint`
  - `npm run typecheck`
  - `npm run test -- --run`
  - `npm run build`

## 停止方法
- 開発サーバーは `Ctrl+C`
- Docker Compose は `docker compose down`

## DB 初期化方法
- SQLite 利用時: `backend/db.sqlite3` を削除して `migrate`
- Docker/PostgreSQL 利用時: `docker compose down -v`

## よくあるエラー
- CSRF エラー時は `/api/v1/auth/csrf/` が取得できているか確認
- ログインできない場合は `is_active` と `employment_status` を確認
- `seed_dev` は `DEBUG=1` のときだけ実行可能
- `DJANGO_DEBUG=0` では `DJANGO_SECRET_KEY` の設定が必須
