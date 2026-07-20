# 0015 Labor Cost Estimates

## Status

Accepted

## Context

Phase 11 introduces wage-rate and allowance settings so managers can review monthly labor cost estimates after attendance closing. The feature handles confidential compensation data and must remain separate from formal payroll processing.

## Decision

We treat the feature as `概算人件費` only. API names, UI labels, CSV columns, and audit metadata use estimate language and avoid payroll-finalization wording.

Staff compensation profiles and allowance assignments are effective-period masters. Active overlapping periods are rejected so historical estimate inputs can be reasoned about without overwriting past settings.

Finalized labor cost estimates store immutable record snapshots, staff summaries, allowance snapshots, `content_hash`, and `validation_fingerprint`. Later edits to wage-rate or allowance masters do not change the finalized estimate.

Wage-rate and labor-estimate APIs and screens are restricted to `system_admin` and `shift_manager`. `supervisor`, `staff`, and `viewer` receive 403 and do not see menu entries.

Tax, social insurance, statutory overtime/night/holiday premium calculation, paid leave balances, payslips, bank transfer data, PDF/Excel export, and external payroll/accounting integrations are outside Phase 11.

Staff self-service screens do not show wage rates or estimate totals. Phase 11 is a management estimate and not a staff payslip or pay-statement feature.

CSV exports use UTF-8 with BOM so Japanese headers and staff names open correctly in common spreadsheet applications.

## Consequences

Managers can review approximate monthly labor costs based on closed attendance snapshots while preserving auditability and reproducibility. Formal payroll remains a later, separately controlled domain with stricter legal and integration requirements.
