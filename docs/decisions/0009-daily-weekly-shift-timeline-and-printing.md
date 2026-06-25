# ADR 0009: Daily and Weekly Shift Timeline and Printing

## Status

Accepted

## Context

Phase 5 needs daily and weekly timeline views for saved monthly shifts. The feature is focused on viewing, confirmation, and printing. It must keep historical display values stable, avoid N+1 queries, and avoid generating large DOM grids.

## Decision

- Use one Timeline API, `/api/v1/monthly-shift-plans/{id}/timeline/`, for both daily and weekly views.
- Limit the requested range to seven days and clamp ranges that cross the plan month to dates inside the plan month.
- Use MonthlyShiftAssignment and MonthlyShiftSegment snapshot fields as display values.
- Keep next-day work on the assignment start date row by using offset minutes up to 2880.
- Assign overlapping segments to deterministic lanes with interval partitioning.
- Fetch StaffCapability records in bulk and reuse the shared capability warning lookup used by the monthly matrix.
- Draw the 15-minute grid with CSS backgrounds and render only staff rows and segment bars as DOM elements.
- Use browser printing through `window.print()` plus print CSS.
- Keep editing in the monthly shift screen and provide a deep link from timeline detail.

## Consequences

The timeline response can serve both daily and weekly layouts with one permission and filtering surface. Historical shifts do not change when WorkType, WorkArea, or pattern names change. Large timelines avoid `days * staff * 96` cell DOM growth. Browser printing is simpler than server-side PDF generation, but final PDF output depends on the browser print dialog and user paper settings.

Server-side PDF, file storage, Excel/CSV export, drag editing, and direct timeline editing remain outside this phase.
