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

## Windows での起動方法
- `scripts/bootstrap.ps1`
- `backend` で `python manage.py runserver`
- `frontend` で `npm run dev`

## Docker Compose 起動方法
- `docker compose up --build`

## 開発用ユーザー
- すべての初期ユーザーのパスワード: `DevPassword123!`
- `system_admin`
- `shift_manager`
- `supervisor`
- `staff`
- `viewer`

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
