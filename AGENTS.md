# FindManager AGENTS

## アーキテクチャ
- Backend は Django 5.2 + DRF、Frontend は React + Vite。
- 認証は Django セッション認証と CSRF を使用する。
- API は `/api/v1/` でバージョニングする。

## 実装ルール
- UUID 主キーを維持する。
- タイムゾーンは `Asia/Tokyo` を維持する。
- スタッフを物理削除しない。
- 権限判定はフロント表示だけでなく API 側で必ず検証する。
- 変更時は必要なマイグレーションを必ず含める。
- 無関係なファイルを変更しない。
- 既存テストを削除して通さない。
- 範囲外機能を先行実装しない。

## コマンド
- Backend 起動: `python manage.py runserver`
- Frontend 起動: `npm run dev`
- Backend テスト: `pytest`
- Frontend テスト: `npm run test -- --run`

## 品質ゲート
- `ruff check .`
- `ruff format --check .`
- `pytest`
- `python manage.py makemigrations --check`
- `python manage.py check`
- `npm run lint`
- `npm run typecheck`
- `npm run test -- --run`
- `npm run build`
