# 0005 Operations Master Models

## Status

Accepted

## Decision

Model locations, work areas, work categories, work types, and work type availability in a dedicated `operations` Django app.

## Consequences

- Operational master data is isolated from account management concerns.
- APIs can evolve independently inside `/api/v1/`.
- Future scheduling and booking features can reuse stable operational master identifiers.
