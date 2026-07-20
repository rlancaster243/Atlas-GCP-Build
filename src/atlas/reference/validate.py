"""Reference-architecture and evidence-index validator (Sprint 8, Phase 8/18).

``python -m atlas.reference.validate`` fails (exit 1) when:

- a referenced file/ADR/evidence path is missing,
- duplicate document ids or claim ids exist,
- required fields are missing,
- a document status or claim status is outside the controlled vocabulary,
- a LIVE claim is backed only by documentation (not real live evidence),
- a blocked claim is presented as complete,
- a verification/last-verified commit is absent,
- a current document references a command whose script does not exist.

Pure/offline: no credentials, no network. Repository files are the only input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from atlas.config.settings import atlas_root

MANIFEST_REL = "docs/reference-architecture/reference-manifest.yml"
EVIDENCE_REL = "governance/generated/evidence-index.json"

DOC_STATUSES = {"CURRENT", "HISTORICAL", "SUPERSEDED", "PLANNED", "BLOCKED"}
CLAIM_STATUSES = {
    "PROVEN_LIVE",
    "PROVEN_STATIC",
    "PROVEN_TEST",
    "PLANNED",
    "BLOCKED",
    "NOT_APPLICABLE",
}
EVIDENCE_TYPES = {
    "TEST",
    "CI_RUN",
    "LIVE_DEPLOYMENT",
    "LIVE_QUERY",
    "DRY_RUN",
    "INCIDENT",
    "RECOVERY",
    "DOCUMENTED_DECISION",
    "CONFIGURATION",
    "CODE_INSPECTION",
}
# Evidence types that count as "live" proof.
LIVE_EVIDENCE_TYPES = {"LIVE_DEPLOYMENT", "LIVE_QUERY", "INCIDENT", "RECOVERY"}
# Evidence types that are only documentation (never sufficient for a LIVE claim).
DOC_ONLY_EVIDENCE_TYPES = {"DOCUMENTED_DECISION"}

MANIFEST_REQUIRED_FIELDS = (
    "document_id",
    "title",
    "purpose",
    "audience",
    "status",
    "source_of_truth",
    "last_verified_commit",
    "owner",
)
MANIFEST_PATH_FIELDS = (
    "source_of_truth",
    "related_adrs",
    "related_runbooks",
    "related_tests",
    "related_evidence",
)
CLAIM_REQUIRED_FIELDS = (
    "claim_id",
    "claim",
    "scope",
    "evidence_type",
    "evidence_path",
    "live_or_static",
    "verification_commit",
)

# A crude command reference matcher: `bash scripts/foo.sh` / `python -m atlas.x`.
_SCRIPT_RE = re.compile(r"\b(?:bash|sh)\s+(scripts/[A-Za-z0-9_./-]+\.(?:sh|py))")


class ReferenceError(ValueError):
    """Raised when the reference package cannot be loaded."""


def _root() -> Path:
    return atlas_root()


def _resolve(rel: str) -> Path:
    return _root() / rel


def load_manifest() -> dict[str, Any]:
    path = _resolve(MANIFEST_REL)
    if not path.exists():
        raise ReferenceError(f"missing reference manifest: {MANIFEST_REL}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ReferenceError("reference manifest is not a mapping")
    return data


def load_evidence_index() -> dict[str, Any]:
    path = _resolve(EVIDENCE_REL)
    if not path.exists():
        raise ReferenceError(f"missing evidence index: {EVIDENCE_REL}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ReferenceError("evidence index is not a mapping")
    return data


def _as_path_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def validate_manifest(manifest: dict[str, Any] | None = None) -> list[str]:
    """Return human-readable errors for the reference manifest (empty = OK)."""
    if manifest is None:
        manifest = load_manifest()
    errors: list[str] = []
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        return ["reference manifest has no 'documents' list"]

    seen_ids: set[str] = set()
    for entry in documents:
        if not isinstance(entry, dict):
            errors.append("manifest document entry is not a mapping")
            continue
        doc_id = str(entry.get("document_id", "")).strip()
        label = doc_id or "<missing id>"

        for field in MANIFEST_REQUIRED_FIELDS:
            value = entry.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{label}: missing required field '{field}'")

        if doc_id:
            if doc_id in seen_ids:
                errors.append(f"duplicate document_id '{doc_id}'")
            seen_ids.add(doc_id)

        status = str(entry.get("status", "")).strip()
        if status and status not in DOC_STATUSES:
            errors.append(f"{label}: invalid status '{status}'")

        # Referenced files must exist.
        for field in MANIFEST_PATH_FIELDS:
            for rel in _as_path_list(entry.get(field)):
                if not _resolve(rel).exists():
                    errors.append(f"{label}: {field} path not found: {rel}")

        # CURRENT documents must not reference nonexistent scripts.
        if status == "CURRENT":
            src = str(entry.get("source_of_truth", "")).strip()
            if src.endswith(".md") and _resolve(src).exists():
                text = _resolve(src).read_text(encoding="utf-8")
                for match in _SCRIPT_RE.finditer(text):
                    rel = match.group(1)
                    if not _resolve(rel).exists():
                        errors.append(f"{label}: references missing script '{rel}'")
    return errors


def _evidence_is_doc_only(claim: dict[str, Any]) -> bool:
    etype = str(claim.get("evidence_type", "")).strip()
    return etype in DOC_ONLY_EVIDENCE_TYPES


def validate_evidence_index(index: dict[str, Any] | None = None) -> list[str]:
    """Return human-readable errors for the evidence index (empty = OK)."""
    if index is None:
        index = load_evidence_index()
    errors: list[str] = []
    claims = index.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["evidence index has no 'claims' list"]

    seen: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("claim entry is not a mapping")
            continue
        claim_id = str(claim.get("claim_id", "")).strip()
        label = claim_id or "<missing claim_id>"

        for field in CLAIM_REQUIRED_FIELDS:
            value = claim.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{label}: missing required field '{field}'")

        if claim_id:
            if claim_id in seen:
                errors.append(f"duplicate claim_id '{claim_id}'")
            seen.add(claim_id)

        etype = str(claim.get("evidence_type", "")).strip()
        if etype and etype not in EVIDENCE_TYPES:
            errors.append(f"{label}: invalid evidence_type '{etype}'")

        live_or_static = str(claim.get("live_or_static", "")).strip().upper()

        # Evidence path must resolve (skip external run ids like CI runs).
        for rel in _as_path_list(claim.get("evidence_path")):
            if not _resolve(rel).exists():
                errors.append(f"{label}: evidence_path not found: {rel}")

        # A LIVE claim cannot be backed only by documentation.
        if live_or_static == "LIVE":
            if _evidence_is_doc_only(claim):
                errors.append(f"{label}: LIVE claim has documentation-only evidence")
            if etype in {"CONFIGURATION", "CODE_INSPECTION"}:
                errors.append(f"{label}: LIVE claim backed only by static {etype}")

        # Blocked work must not be presented as complete.
        status = str(claim.get("status", "")).strip().upper()
        if status == "BLOCKED":
            if live_or_static == "LIVE" and etype in LIVE_EVIDENCE_TYPES:
                errors.append(f"{label}: BLOCKED claim presented with live evidence")
            completed_flag = claim.get("completed")
            if completed_flag is True:
                errors.append(f"{label}: BLOCKED claim marked completed=true")
        if status and status not in CLAIM_STATUSES:
            errors.append(f"{label}: invalid status '{status}'")

    return errors


def validate_all() -> list[str]:
    """Validate both the manifest and the evidence index."""
    errors: list[str] = []
    try:
        errors.extend(validate_manifest())
    except ReferenceError as exc:
        errors.append(str(exc))
    try:
        errors.extend(validate_evidence_index())
    except ReferenceError as exc:
        errors.append(str(exc))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Atlas reference package")
    parser.add_argument(
        "--only",
        choices=["manifest", "evidence", "all"],
        default="all",
        help="which artifact to validate (default: all)",
    )
    args = parser.parse_args(argv)

    if args.only == "manifest":
        errors = validate_manifest()
    elif args.only == "evidence":
        errors = validate_evidence_index()
    else:
        errors = validate_all()

    if errors:
        print("reference validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("reference validation OK: manifest + evidence index consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
