# 0018 Production Readiness

## Status

Accepted

## Context

FindManager has reached a release-candidate boundary after completing the operational workflows from authentication through monthly revenue and labor-cost performance. Production operation now requires repeatable configuration checks, observable failures, recovery procedures, and representative end-to-end verification without introducing another business domain.

## Decision

Production-sensitive Django settings are controlled by environment variables. A production process must fail fast when `DEBUG` is enabled, the secret key is missing or weak, or allowed hosts and CSRF origins are unsafe. This keeps deploy-time secrets and host-specific values out of source control and container images while preserving convenient local defaults in development.

`/api/v1/health/` only proves that the application process can answer HTTP. `/api/v1/readiness/` separately checks the database, migration state, and required settings. Keeping them separate allows an orchestrator to distinguish a live process from one that must not yet receive traffic, without returning internal connection details.

Every request receives a safe request ID. The same value is included in structured request logs and normalized error responses so an operator can correlate a user-visible failure with server logs. Client-supplied IDs are accepted only in a restricted format; other values are replaced.

Logs use an explicit metadata allowlist. Passwords, cookies, CSRF and authorization values, secret keys, phone numbers, individual rates or labor costs, and revenue line details are never logged. Financial and personal data remain available only through authorized application paths, not through operational telemetry.

Playwright covers nine representative cross-domain workflows rather than every UI branch. Unit and API tests retain detailed edge-case coverage; the E2E suite verifies that authentication, CSRF, routing, and the critical monthly workflow transitions work together within a practical CI duration. E2E uses a dedicated seeded database and no production data.

Backups are not considered complete until restoration has been rehearsed and application-level checks pass against the restored database. The runbook therefore pairs `pg_dump` with `pg_restore`, migration checks, integrity checks, and a smoke test.

Phase 14 prepares deployable images, CI checks, environment contracts, and operating procedures, but does not deploy to a production server. Hosting, DNS, certificates, secret registration, monitoring providers, and production data remain deployment-owner decisions and require an approved change window.

The system can be treated as a release candidate when all backend, frontend, permission, leakage, and E2E tests pass; migrations and deploy checks are clean; dependency audits have no blocking findings; health and readiness pass; recovery and operating procedures exist; CI is green; and the committed working tree is clean. It is not a claim of formal payroll, accounting, tax, or legal compliance.

## Consequences

Deployments become environment-specific without rebuilding source artifacts, failures can be correlated without exposing sensitive values, and operators have explicit setup, release, backup, restore, and incident procedures. A release still requires infrastructure review, restore rehearsal, production secret provisioning, smoke testing, and an explicit rollback decision.
