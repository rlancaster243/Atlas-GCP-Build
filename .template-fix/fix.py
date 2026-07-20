from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

repo = Path.cwd()
source = Path(os.environ["RUNNER_TEMP"]) / "source" / "atlas-template"

copies = [
    "docs/evidence-sprint7/cost-guard-block.txt",
    "docs/evidence-sprint8/clean-clone-results.md",
    "docs/evidence-sprint8/independent-handoff-results.md",
    "governance/generated/evidence-index.json",
    "scripts/validate_public_extraction.py",
]
substitutions = {
    "vital-scout-479118-n7": "example-gcp-project",
    "911571548652": "123456789012",
    "rlancaster243/DE-project-1": "YOUR_GITHUB_OWNER/YOUR_REPOSITORY",
    "rlancaster243": "YOUR_GITHUB_OWNER",
    "DE-project-1": "Atlas-GCP-Build",
    "russell_lancaster243@gmail.com": "<operator-email>",
}

for rel in copies:
    src = source / rel
    dst = repo / rel
    if not src.is_file():
        raise SystemExit(f"missing source artifact: {rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    text = dst.read_text(encoding="utf-8")
    for old, new in substitutions.items():
        text = text.replace(old, new)
    dst.write_text(text, encoding="utf-8")

(repo / "config/public_extraction_manifest.yml").write_text(
    """# Public extraction manifest for the standalone Atlas template.
version: 1
repository_published: true
last_verified_commit: "template-extraction"

global_substitutions:
  - identifier: gcp_project_id
    example_value_class: source sandbox GCP project id
    occurrences_scope: docs, configs, scripts
    disposition: REPLACE_WITH_SAMPLE
    replacement_strategy: configure ATLAS_GCP_PROJECT_ID
  - identifier: github_repository
    example_value_class: source private repository identity
    occurrences_scope: WIF docs and scripts
    disposition: REPLACE_WITH_SAMPLE
    replacement_strategy: configure ATLAS_GITHUB_REPOSITORY
  - identifier: operator_identity
    example_value_class: personal notification identity
    occurrences_scope: operational evidence and runbooks
    disposition: REPLACE_WITH_SAMPLE
    replacement_strategy: configure notification identity outside Git

detector_allowlist:
  - scripts/validate_ci.sh
  - src/atlas/ops/audit.py
  - tests/unit/test_audit.py
  - tests/unit/test_security_policy.py
files: []
cleared_categories:
  - committed credentials / service-account keys / tokens: none
  - authorization headers in evidence: none
  - private webhook URLs: none
  - real user data: none (synthetic only)
  - personal notification addresses: replaced with placeholders
  - source sandbox project identifiers: replaced with examples
""",
    encoding="utf-8",
)

(repo / "docs/reference-architecture/public-extraction-review.md").write_text(
    """# Public-Repository Extraction Review

**Status:** CURRENT

This standalone repository was extracted from the Atlas reference implementation.
The public candidate was scanned for personal email addresses, private keys,
service-account JSON, API keys, webhook URLs, bearer tokens, source sandbox
identifiers, and real user data. No committed credentials or real user data are
included. Runtime identities and GCP resource names use documented examples or
environment variables.

The extraction excludes the separate artifact-hosting product and raw drill
evidence bundles that are not required by this data-platform template. Selected
sanitized evidence remains where reference and regression gates require it.
Historical reports do not prove that a new adopter has deployed this template.

```bash
python scripts/validate_public_extraction.py
```
""",
    encoding="utf-8",
)

(repo / "docs/reference-architecture/template-extraction-plan.md").write_text(
    """# Template Extraction Record

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
""",
    encoding="utf-8",
)

readme = repo / "README.md"
text = readme.read_text(encoding="utf-8")
if "git checkout main" not in text:
    marker = "```bash\ncp .env.example .env\n"
    if marker not in text:
        raise SystemExit("README quick-start marker not found")
    text = text.replace(
        marker,
        "```bash\ngit checkout main\ngit pull --ff-only origin main\ncp .env.example .env\n",
        1,
    )
if "atlas-sprint-3-complete" not in text:
    marker = "A new deployment is complete only after its own CI, isolated cloud validation,\n"
    if marker not in text:
        raise SystemExit("README evidence marker not found")
    text = text.replace(
        marker,
        "The reference release lineage includes `atlas-sprint-3-complete` for the "
        "orchestrated platform milestone and later Sprint 8 handoff evidence.\n\n"
        + marker,
        1,
    )
readme.write_text(text, encoding="utf-8")

manifest = repo / "docs/reference-architecture/reference-manifest.yml"
text = manifest.read_text(encoding="utf-8")
text = text.replace(
    "purpose: Private-data review and dispositions (no publication)",
    "purpose: Public-template extraction review and current dispositions",
)
text = text.replace("title: Template-Extraction Plan", "title: Template Extraction Record")
text = text.replace(
    "purpose: Future template plan (not executed in Sprint 8)",
    "purpose: Record of the completed standalone-template extraction",
)
text, count = re.subn(
    r"(document_id: template-extraction-plan[\s\S]*?status:) PLANNED",
    r"\1 CURRENT",
    text,
    count=1,
)
if count != 1:
    raise SystemExit("reference manifest extraction status not updated")
manifest.write_text(text, encoding="utf-8")

shutil.rmtree(repo / ".template-fix")
print("extraction contracts repaired")
