# 0016 Labor Cost Budget And Variance

## Status

Accepted

## Context

Phase 12 compares a manager-defined monthly labor cost budget with planned shift cost and the Phase 11 attendance-based actual estimate. These values are confidential estimates and must remain reproducible without becoming a formal payroll or accounting subsystem.

## Decision

Budget, planned labor cost, and actual estimate are separate concepts. The budget is a management target, planned cost is calculated from shifts, and actual estimate is calculated from attendance. Keeping them separate makes each variance understandable and prevents an operational estimate from being presented as a payment amount.

The feature continues to use estimate terminology because it does not calculate statutory overtime, night or holiday premiums, tax, social insurance, deductions, or final payroll. It therefore cannot represent formal pay.

An active publication is the preferred planned-cost source because it is the schedule communicated to staff and is already an immutable operational snapshot. A confirmed plan is the approval-capable fallback. A draft plan can be previewed for planning but cannot be approved.

Approval stores plan-record, staff, daily, and allowance snapshots. Later shift, compensation, and allowance edits therefore do not rewrite the approved planned-cost view.

Current actual estimate values are excluded from the budget `content_hash`. Actual attendance and Phase 11 estimates may continue changing after budget approval, while the approved budget and planned-cost inputs must retain a stable identity.

Approval issues and comparison issues are separate. Shift-source, compensation, allowance, calculation, and planned-budget warnings participate in approval and `validation_fingerprint`; actual estimate availability and actual-budget thresholds are comparison-only and do not block approval.

Budget, planned cost, actual estimate, rates, and allowances are restricted to `system_admin` and `shift_manager`. Supervisor and staff workflows must not reveal confidential compensation or labor-cost values through either API or UI.

Sales budgets and labor-cost ratios are excluded because Phase 12 has no sales domain or accounting allocation model. Automatic shift optimization, reduction, and reassignment are also excluded because the phase provides decision data, not an automated staffing decision engine.

CSV is encoded as UTF-8 with BOM so Japanese headers, locations, and staff names open correctly in common spreadsheet applications without manual encoding selection.

## Consequences

Managers can approve a reproducible monthly budget and planned-cost baseline, then compare it with the latest actual estimate without mutating that baseline. Formal payroll, accounting, sales analysis, and optimization remain separate future domains.
