#!/usr/bin/env python3
"""Public-repository extraction review validator (Sprint 8, Phase 14).

Dry-run by default. Scans the in-scope repository for private/sensitive patterns
and verifies that every file containing a *forbidden-public* pattern is given an
explicit disposition in ``config/public_extraction_manifest.yml``.

Guarantees:
- never prints a matched secret value (only file paths + pattern ids),
- never pushes a repository, changes visibility, publishes artifacts, or removes
  private evidence from the primary repository,
- exits nonzero on any unresolved sensitive file or manifest error.

Under ``ATLAS_APPROVE_PUBLIC_EXTRACTION=true`` with ``--emit-candidate <dir>`` it
may copy PUBLIC_READY files into a *local* candidate directory for inspection.

Usage:
  python scripts/validate_public_extraction.py            # dry-run report + check
  python scripts/validate_public_extraction.py --emit-candidate /tmp/atlas-public
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent  # project-atlas/
MANIFEST_REL = "config/public_extraction_manifest.yml"

VALID_DISPOSITIONS = {
    "PUBLIC_READY",
    "REDACT",
    "REPLACE_WITH_SAMPLE",
    "EXCLUDE",
    "PRIVATE_ONLY",
    "REVIEW_REQUIRED",
}

# Out-of-scope trees (separate lifecycle) and non-source dirs.
EXCLUDED_DIR_PARTS = {
    ".git",
    "artifact-platform",
    "node_modules",
    "__pycache__",
    "target",
    ".venv",
    "dist",
    "data",
    "logs",
    ".gcp",
}

# Patterns that must NEVER appear in a PUBLIC_READY file. Built so this file
# itself contains no literal secret (regex fragments only).
FORBIDDEN_PUBLIC = {
    "personal_email": re.compile(r"[A-Za-z0-9._%+-]+@(?:gmail|yahoo|hotmail|outlook)\.com", re.IGNORECASE),
    "private_key_header": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "gcp_api_key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "service_account_json": re.compile(r'"type"\s*:\s*"service_account"'),
    "slack_webhook": re.compile(r"https://hooks\.slack\.com/services/\S+"),
    "bearer_literal": re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._-]{12,}"),
}

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".sh",
    ".yaml",
    ".yml",
    ".json",
    ".sql",
    ".txt",
    ".cfg",
    ".ini",
    ".toml",
}


def _in_scope(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts)
    return not (parts & EXCLUDED_DIR_PARTS)


def _iter_text_files() -> list[Path]:
    """Enumerate git-tracked, in-scope text files (never gitignored venvs/data)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(ROOT),
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"cannot list tracked files: {exc}") from exc

    files: list[Path] = []
    for rel in out.split("\0"):
        if not rel:
            continue
        path = ROOT / rel
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if not path.is_file():
            continue
        if not _in_scope(path):
            continue
        files.append(path)
    return files


def load_manifest() -> dict:
    path = ROOT / MANIFEST_REL
    if not path.exists():
        raise SystemExit(f"missing manifest: {MANIFEST_REL}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("manifest is not a mapping")
    return data


def manifest_dispositions(manifest: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in manifest.get("files", []) or []:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path", "")).strip()
        disp = str(entry.get("disposition", "")).strip()
        if rel:
            result[rel] = disp
    return result


def detector_allowlist(manifest: dict) -> set[str]:
    """Files that define/test the scanners: their pattern strings are detector
    definitions or fixtures, not real secrets (mirrors gate_secret_scan)."""
    allow = {"scripts/validate_public_extraction.py", MANIFEST_REL}
    for rel in manifest.get("detector_allowlist", []) or []:
        allow.add(str(rel).strip())
    return allow


def scan(manifest: dict | None = None) -> dict[str, list[str]]:
    """Return {relpath: [pattern_ids]} for files with forbidden-public matches."""
    allow = detector_allowlist(manifest or {})
    findings: dict[str, list[str]] = {}
    for path in _iter_text_files():
        rel = str(path.relative_to(ROOT))
        if rel in allow:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = [pid for pid, rx in FORBIDDEN_PUBLIC.items() if rx.search(text)]
        if hits:
            findings[rel] = sorted(hits)
    return findings


def validate(manifest: dict) -> tuple[list[str], dict[str, list[str]]]:
    errors: list[str] = []

    for entry in manifest.get("files", []) or []:
        disp = str(entry.get("disposition", "")).strip()
        rel = str(entry.get("path", "")).strip()
        if disp not in VALID_DISPOSITIONS:
            errors.append(f"{rel or '<no path>'}: invalid disposition '{disp}'")
        for field in ("reason", "replacement_strategy"):
            if disp != "PUBLIC_READY" and not str(entry.get(field, "")).strip():
                errors.append(f"{rel}: missing '{field}' for non-public disposition")

    dispositions = manifest_dispositions(manifest)
    findings = scan(manifest)

    for rel, pattern_ids in findings.items():
        disp = dispositions.get(rel)
        if disp is None:
            errors.append(
                f"{rel}: contains forbidden-public pattern "
                f"({', '.join(pattern_ids)}) but has no manifest disposition"
            )
        elif disp == "PUBLIC_READY":
            errors.append(
                f"{rel}: marked PUBLIC_READY but contains forbidden-public pattern ({', '.join(pattern_ids)})"
            )

    return errors, findings


def emit_candidate(manifest: dict, dest: Path) -> None:
    import shutil

    dispositions = manifest_dispositions(manifest)
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in _iter_text_files():
        rel = str(path.relative_to(ROOT))
        disp = dispositions.get(rel, "PUBLIC_READY")
        if disp in {"EXCLUDE", "PRIVATE_ONLY", "REVIEW_REQUIRED"}:
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    print(f"candidate emitted: {copied} files -> {dest} (no publication performed)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas public-extraction review")
    parser.add_argument(
        "--emit-candidate",
        metavar="DIR",
        help="copy public-safe files into a local candidate dir "
        "(requires ATLAS_APPROVE_PUBLIC_EXTRACTION=true)",
    )
    args = parser.parse_args(argv)

    manifest = load_manifest()
    errors, findings = validate(manifest)

    print("Public-extraction dry-run report:")
    print(f"  files with forbidden-public patterns: {len(findings)}")
    for rel, pattern_ids in sorted(findings.items()):
        disp = manifest_dispositions(manifest).get(rel, "<none>")
        print(f"    - {rel}: {', '.join(pattern_ids)} -> disposition {disp}")

    if errors:
        print("public-extraction validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("public-extraction validation OK: all sensitive files have dispositions")

    if args.emit_candidate:
        if os.environ.get("ATLAS_APPROVE_PUBLIC_EXTRACTION") != "true":
            print(
                "refusing to emit candidate: set ATLAS_APPROVE_PUBLIC_EXTRACTION=true",
                file=sys.stderr,
            )
            return 2
        emit_candidate(manifest, Path(args.emit_candidate))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
