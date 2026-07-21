# 0017 Revenue Performance Management

## Status

Accepted

## Context

Phase 13 combines monthly revenue targets and manually entered actual revenue with the approved labor-cost budget, planned shift cost, and finalized actual labor-cost estimate. These values are highly confidential operational management data. They must be reproducible without being presented as formal accounting, tax, or payroll results.

## Decision

Revenue budget and revenue actual are separate monthly periods. A budget is a management target, while an actual is an operationally entered result. Revenue categories belong to a location because each club can use a different management breakdown. Category code and name are copied into lines and immutable snapshots so later master changes do not rewrite history.

Revenue budget approval stores a stable content hash and validation fingerprint. Revenue actual finalization requires an approved revenue budget, an approved labor-cost budget, and a finalized labor-cost estimate. It atomically creates a monthly performance snapshot and category snapshots. Reopening preserves the workflow history, and refinalization replaces the one-to-one current snapshot inside the same transaction.

All currency and percentage calculations use `Decimal` with `ROUND_HALF_UP`. Revenue variance is actual minus budget. Every labor-cost ratio uses the corresponding labor-cost amount as numerator and the selected revenue amount as denominator. A ratio is `NULL` when its denominator is zero. Revenue attainment is `0.00` when budget and actual are both zero; it is `NULL` when budget is zero and actual is positive. Both cases produce a warning.

The `labor_cost_ratio_high` warning uses a fixed 40 percent threshold in Phase 13. It is an advisory display warning rather than a configurable accounting rule and never blocks finalization by itself.

Only `system_admin` and `shift_manager` may access revenue, labor-cost, or ratio APIs and screens. Authorization occurs before serializer validation. Supervisors, staff, viewers, and self-service responses must not expose these values.

This feature is operational monthly performance management. It does not provide journals, tax treatment, formal payroll, member-system or SLIM integration, invoicing, allocations, forecasts, or automatic staffing decisions.

CSV exports use UTF-8 with BOM so Japanese headers, location names, and category names open correctly in common spreadsheet applications.

## Consequences

Managers can reproduce the values used at finalization and compare revenue with planned and estimated labor cost without silently changing historical results. Live fallbacks remain useful during preparation, but explicit warnings distinguish them from approved or finalized sources.
