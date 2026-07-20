# Template Extraction Record

**Status:** CURRENT

The Atlas reference implementation has been extracted into this standalone GCP
production-data-platform template. Reusable CI, keyless delivery, migrations,
recovery, observability, governance, schema, lineage, cost, and handoff controls
are retained. Cloud projects, repository claims, service accounts, buckets,
datasets, schedules, notifications, and cost ceilings are configuration.

Extraction proves repository portability. Operational adoption still requires an
isolated GCP deployment, a successful batch, a deliberate failure, targeted
recovery, governance and observability checks, cleanup, and operator handoff.
Each adopter must produce environment-specific evidence before making production
readiness claims.
