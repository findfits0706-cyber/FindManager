# 0008 Monthly Shift Snapshots and Generation

## Status

Accepted

## Context

Phase 4 turns reusable weekly templates into concrete dated monthly shifts. Once a monthly shift is created, later master or template edits must not silently change the historical schedule that managers are editing.

## Decision

MonthlyShiftPlan stores the location and target year/month separately from individual assignments. This keeps monthly locking, generation metadata, and matrix retrieval centered on one aggregate.

MonthlyShiftAssignment represents one staff member on one work date within a plan. The active uniqueness rule is plan/date/staff because the current operational model is one row per staff per day. Cross-location conflicts are intentionally left for a later phase.

MonthlyShiftSegment copies the selected ShiftPatternSegment rows. It stores WorkType and WorkArea names, short names, color keys, and break flags as snapshots. Assignment also stores the pattern code, name, and short name snapshots. This preserves the monthly schedule if ShiftPattern, WorkType, or WorkArea records are renamed or deactivated after generation.

Weekly template changes do not mutate already created monthly shifts. Managers can reapply a template explicitly. `skip_existing` protects all existing active cells. `replace_template_generated` replaces only template-generated, non-customized assignments. Manual and customized assignments are protected because they represent manager edits.

Generation supports `strict` and `skip_invalid`. `strict` is safest for full-month generation because any error blocks apply. `skip_invalid` supports partial generation while making skipped/error counts explicit.

StaffLocation and StaffCapability are validated in Phase 4 because assignments finally have concrete dates. `independent` and `trainer` pass, `assisted` and `trainee` produce warnings, and missing required capability is an error.

The monthly screen uses a staff-by-date grid. The detailed 15-minute timeline, print/PDF views, and advanced cross-location conflict detection are deferred to later phases to keep this phase focused on durable monthly data and safe generation.

## Consequences

Template apply recalculates candidates inside a transaction and records one aggregate audit event. Segment removal is soft deactivation, and previously inactive omitted segments are not resaved, preserving history timestamps.
