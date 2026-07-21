# 日次運用手順

## 開始時確認

1. `/api/v1/health/`と`/api/v1/readiness/`が正常であることを確認する。
2. system adminは必要に応じて`/system/status`で未処理件数と最終監査日時を確認する。
3. 500やlogin失敗の増加がないか、request ID付き構造化ログを確認する。ログへ秘密値や財務明細を出さない。

## 希望確認

- 対象月・拠点と受付期間を確認し、submitted/lockedの希望をmanager画面で確認する。
- returnedにする場合は、本人が修正できる具体的理由を残す。
- 希望はシフト作成時のwarningであり、自動的な勤務確約ではないことを共有する。

## シフト変更申請

- submitted申請の対象公開snapshot、申請種別、日付、代替staff、希望時間を確認する。
- approveだけでは公開シフトは変わらない。apply後は公開がwithdrawされるため、変更後の月間planを再確認してrepublishする。
- 同じ申請を二重applyしない。terminal statusと監査eventを確認する。

## 打刻異常

- 未退勤、休憩中のまま、時刻逆転、予定との差を当日中に確認する。
- 本人の原eventは消さず、必要に応じて修正申請またはmanager adjustmentを使用する。
- confirmedまたはclosed月を無断で変更しない。解除が必要なら理由と責任者を記録する。

## 勤怠修正

- 本人申請の対象日、理由、希望時刻、既存eventを照合する。
- approve後にapplyし、結果の勤務時間・休憩・warningと監査eventを確認する。
- reject時は理由を記録する。口頭依頼だけで原記録を上書きしない。

## 未処理申請

- 希望休、シフト変更、勤怠修正のsubmitted/approved未applyを日次で確認する。
- 長期滞留、締め対象月、公開済みシフトへ影響するものを優先する。
- 件数が画面と`/system/status`で大きく異なる場合はfilter、role、対象拠点を確認し、必要ならincidentとして扱う。

## 終了時確認

- 当日分の重大な打刻異常と未処理申請の担当・期限を記録する。
- データ修正、承認、reopen、再公開を行った場合は監査eventとrequest IDを残す。
- 障害兆候がある場合は[障害対応手順](incident-response.md)へ切り替える。
