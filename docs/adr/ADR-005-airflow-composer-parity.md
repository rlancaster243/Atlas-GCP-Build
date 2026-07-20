# ADR-005: Airflow Composer Parity Pins

## Status

Accepted — 2026-07-14
Amended — 2026-07-18 (Sprint 4: Composer image revised to `build.13`)

## Context

Sprint 3 introduces local Airflow orchestration that must behave consistently with
Cloud Composer before production deployment.

## Decision

Pin local Airflow to **3.1.7** with Google provider **20.0.0** and Standard provider
**1.12.1**, targeting Composer image `composer-3-airflow-3.1.7-build.12`.

## Sprint 4 amendment — 2026-07-18

The Sprint 4 preflight verified via the Composer API (`us-central1`) that
`composer-3-airflow-3.1.7-build.12` is **no longer offered**. The only available
Composer 3 image carrying Airflow 3.1.7 is:

```
composer-3-airflow-3.1.7-build.13
```

Decision (owner-approved 2026-07-18): target **`composer-3-airflow-3.1.7-build.13`**
for the Sprint 4 managed deployment. The Airflow core version (3.1.7) and the
provider pins above are unchanged; only the Composer build number moved. Provider
compatibility must be re-verified against the live environment during the Sprint 4
smoke run before the release tag is created.

Install core using official Python 3.12 constraints, then apply provider pins and
record `pip check` output in the preflight report.

## Consequences

- Local Python 3.12.3 differs from Composer Python 3.11.8; parse-time helpers must
  remain compatible with both.
- Revisit this ADR if the Composer image is retired or upgraded.
