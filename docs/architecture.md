# Architecture

## システム構成
- Backend: Django + DRF
- Frontend: React + Vite
- DB: PostgreSQL 本番想定、ローカル簡易実行は SQLite 対応
- SQLite は簡易ローカル開発専用
- 正式な開発確認、CI、本番は PostgreSQL を使用
- 予約競合、排他制御、制約の正式検証は PostgreSQL を前提とする
- SQLite のみのテスト成功は完了条件にしない

## 認証方式
- Django セッション認証
- HttpOnly Cookie
- CSRF 保護

## データフロー
- Frontend は `/api/v1/auth/csrf/` で CSRF Cookie を取得
- ログイン成功後はセッション Cookie を利用して API を呼び出す
- スタッフ操作はすべて Backend が権限検証を行う

## 責務分離
- Backend: 認証、権限、監査、スタッフ管理
- Frontend: 日本語 UI、画面遷移、入力バリデーション、通知

## 将来拡張方針
- シフト、施設、予約は accounts/common とは別 app として追加
- API バージョンは `/api/v1/` を維持し、破壊的変更時に次バージョンへ切替
