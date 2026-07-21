# 月次運用手順

月次処理は拠点・対象年月を画面上と作業記録へ明記し、前工程の確定結果を確認してから次へ進みます。金額は運営管理上の概算・予実値です。

## 1. シフト公開

月間シフトのassignment、能力warning、希望、変更申請反映を確認し、confirm、publication preview、warning確認、publishの順に実行します。公開後変更をapplyした場合は必ず再公開します。

## 2. 勤怠確認

全staff・全日について未退勤、休憩、欠損、修正申請、予定差を確認します。必要なmanager adjustment、correction approve/apply、confirmを完了します。

## 3. 勤怠締め

月次closing previewのerrorを解消し、warning内容を保存します。最新`validation_fingerprint`で、warningがあれば明示acknowledgementしてcloseします。閉鎖後の操作拒否とstaff summaryを確認します。

## 4. 概算人件費finalize

単価・手当の適用期間と勤怠closingを確認します。previewの出所、error、warning、合計を確認し、最新fingerprintとacknowledgementでfinalizeします。正式給与として使用しません。

## 5. 人件費予算予実確認

対象月の人件費予算、公開シフト予定原価、finalized概算実績を確認します。未承認ならpreview、warning確認、approveを行い、予算差異・消化率を確認します。

## 6. 売上実績入力

拠点別売上区分へ当月実績をmanual入力します。区分、金額、source、予算との欠落、0円の意味を照合します。会計帳簿や入金消込の代替にしません。

## 7. 売上実績finalize

approved売上予算、approved人件費予算、finalized概算人件費が同一拠点・年月であることを確認します。previewのsource、warning/error、content hash、fingerprintを確認し、必要なacknowledgement後にfinalizeします。

## 8. 人件費率確認

売上予算・実績、予定・実績概算人件費、各分母を確認します。分母0は率が表示不能になる場合があります。40%以上warningは運用上の目安であり、自動判断や会計基準ではありません。

## 9. CSV保存

勤怠closing、概算人件費、人件費予算、売上予算・実績・performanceの必要なCSVをUTF-8 BOMで出力します。閲覧権限、暗号化保存、保持期限を財務情報ポリシーに従って設定し、メールへ無防備に添付しません。

## 10. バックアップ

[バックアップ・復元手順](backup-and-restore.md)に従い、月次完了後のPostgreSQL、media、release tagの対応を保存します。checksumとrestore検証予定を台帳へ記録します。

## 完了記録

各period ID、status、実行者、完了日時、warning acknowledgement、CSV保管先、backup IDを記録します。誤りを発見した場合は独断でDBを直接更新せず、[障害対応手順](incident-response.md)のreopen手順へ進みます。
