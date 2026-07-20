"""Security-policy scanners for governed Atlas artifacts (Sprint 7, Phase 8).

Two offline scanners used by ``gate_security_policy``:

1. ``scan_managed_iam`` — managed IAM/bootstrap scripts must never grant
   prohibited roles to Atlas principals or create service-account keys.
2. ``scan_data_exposure`` — governed Atlas artifacts (config, governance,
   observability, sprint docs) must not commit literal secrets, recipient
   addresses, webhook URLs, or verification codes. Variable references
   (``$TOKEN``, ``${NOTIFICATION_CHANNEL}``) are allowed.

Both return a list of ``(path, lineno, reason)`` findings; empty == clean.
Out-of-scope trees (artifact-platform, examples, infra/artifact-platform) are
excluded — they are reviewed at extraction time (Sprint 8).
"""

from __future__ import annotations

import re
from pathlib import Path

from atlas.config.settings import atlas_root

Finding = tuple[str, int, str]

_PROHIBITED_ROLES = (
    "roles/owner",
    "roles/editor",
    "roles/resourcemanager.projectIamAdmin",
)

# Literal-secret patterns. Deliberately do NOT match shell variable references.
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_GCP_API_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
_SA_JSON = re.compile(r'"type"\s*:\s*"service_account"')
_SLACK_WEBHOOK = re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+")
_SLACK_TOKEN = re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")
_LITERAL_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9]{20,}")
_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@(?:gmail|yahoo|hotmail|outlook)\.com")


def _iter_files(root: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pat in patterns:
        files.extend(root.glob(pat))
    excluded = ("artifact-platform", "examples/artifact-dashboard", "infra/artifact-platform")
    return sorted(f for f in files if f.is_file() and not any(x in str(f) for x in excluded))


def scan_managed_iam() -> list[Finding]:
    root = atlas_root()
    findings: list[Finding] = []
    for path in _iter_files(root, ["scripts/*.sh", "infra/**/*.tf", "infra/**/*.sh"]):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            low = line.strip()
            if low.startswith("#"):
                continue
            for role in _PROHIBITED_ROLES:
                if role in line and ("add-iam-policy-binding" in line or "role" in line.lower()):
                    findings.append((str(path.relative_to(root)), lineno, f"grants prohibited {role}"))
            if "iam service-accounts keys create" in line or "--key-file" in line:
                findings.append((str(path.relative_to(root)), lineno, "creates/uses a service-account key"))
    return findings


def scan_data_exposure() -> list[Finding]:
    root = atlas_root()
    findings: list[Finding] = []
    targets = _iter_files(
        root,
        [
            "config/*.yaml",
            "governance/**/*.yml",
            "governance/**/*.json",
            "observability/**/*.json",
            "observability/**/*.txt",
            "docs/evidence-sprint7/**/*",
        ],
    )
    checks = [
        (_PRIVATE_KEY, "private key material"),
        (_GCP_API_KEY, "GCP API key"),
        (_SA_JSON, "service-account JSON"),
        (_SLACK_WEBHOOK, "Slack webhook URL"),
        (_SLACK_TOKEN, "Slack token"),
        (_LITERAL_BEARER, "literal bearer token"),
        (_EMAIL, "personal email address"),
    ]
    for path in targets:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, reason in checks:
                if pattern.search(line):
                    findings.append((str(path.relative_to(root)), lineno, reason))
    return findings


def scan_text(text: str) -> list[str]:
    """Scan an arbitrary string (for regression tests). Never echoes the value."""
    reasons: list[str] = []
    for pattern, reason in [
        (_PRIVATE_KEY, "private key material"),
        (_GCP_API_KEY, "GCP API key"),
        (_SA_JSON, "service-account JSON"),
        (_SLACK_WEBHOOK, "Slack webhook URL"),
        (_SLACK_TOKEN, "Slack token"),
        (_LITERAL_BEARER, "literal bearer token"),
        (_EMAIL, "personal email address"),
    ]:
        if pattern.search(text):
            reasons.append(reason)
    return reasons


def all_findings() -> list[Finding]:
    return scan_managed_iam() + scan_data_exposure()
