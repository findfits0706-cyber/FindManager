# 0007 Shift Patterns and Weekly Templates

## Status

Accepted

## Context

Phase 3 prepares reusable shift settings before monthly shifts are created. The system needs one-day work sequences and a weekly staff assignment template without creating dated monthly shift records yet.

## Decision

ShiftPattern and WeeklyShiftTemplate are separate models. A ShiftPattern represents the ordered work and break segments for one working day. A WeeklyShiftTemplate references those patterns by staff member and weekday.

Segment time is stored as minutes from midnight. This makes `08:30` become `510` and `翌00:30` become `1470`, allowing next-day work without mixing in real calendar dates. Offsets are restricted to 15-minute increments because the business schedule is managed on quarter-hour boundaries and the UI can present a predictable list of choices.

ShiftPatternSegment and WeeklyShiftTemplateEntry are not physically deleted when removed from a nested edit. They are set inactive so audit history and references remain understandable.

Weekly templates do not validate StaffCapability. A template has only a weekday, not a concrete date, so capability periods cannot be evaluated correctly. Phase 4 will validate StaffLocation, StaffCapability, required capabilities, and overlaps when a template is expanded to dated monthly shifts.

Template changes do not mutate future confirmed shifts. Phase 4 will copy values from templates into monthly shift records, after which those records are independent snapshots.

## Consequences

The API performs nested synchronization in transactions so parent and child rows are saved together or rolled back together. Reactivation re-runs validation rather than merely setting `is_active=True`.
