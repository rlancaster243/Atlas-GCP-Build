"""Consumer-impact analysis for a proposed change (Sprint 7, Phase 5).

Given a governed asset (and optionally a change record), reports the direct and
transitive downstream assets, affected tests, affected contracts, consumers and
owners, and migrations/runbooks involved. Uses only repository artifacts.

Usage::

    python -m atlas.governance.impact --asset fct_events \\
        --change governance/changes/CHG-....yml --output-dir /tmp/impact
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

from atlas.config.settings import atlas_root
from atlas.governance.lineage import build_lineage
from atlas.governance.registry import build_asset_index, load_consumers


def _tests_dir() -> Path:
    return atlas_root() / "dbt" / "atlas_dbt" / "tests"


def _models_dir() -> Path:
    return atlas_root() / "dbt" / "atlas_dbt" / "models"


def _affected_tests(assets: set[str]) -> list[str]:
    """dbt test/property files that reference any affected asset by name."""
    hits: set[str] = set()
    names = {a.split(".")[-1] for a in assets}
    search_roots = [_tests_dir(), _models_dir()]
    for root in search_roots:
        if not root.exists():
            continue
        for path in list(root.glob("**/*.sql")) + list(root.glob("**/*.yml")):
            text = path.read_text(encoding="utf-8")
            for name in names:
                if re.search(rf"\b{re.escape(name)}\b", text):
                    hits.add(str(path.relative_to(atlas_root())))
                    break
    return sorted(hits)


def analyze(asset_id: str, change_file: Path | None = None) -> dict[str, Any]:
    graph = build_lineage()
    index = build_asset_index()
    consumers = load_consumers()

    key = asset_id if asset_id in graph.node_types else asset_id.split(".")[-1]
    direct = sorted(graph.downstream.get(key, set()))
    transitive = sorted(graph.transitive_downstream(key))
    upstream = sorted(graph.transitive_upstream(key))

    affected_assets = set(transitive) | {key}
    # Consumers among the downstream set + any consumer registry entry that reads
    # the asset directly.
    affected_consumers = {n for n in transitive if n in consumers}
    for consumer, spec in consumers.items():
        reads = set(spec.get("reads", []) or [])
        if asset_id in reads or key in {r.split(".")[-1] for r in reads}:
            affected_consumers.add(consumer)

    owners = sorted(
        {
            index[a].get("technical_owner", "?")
            for a in affected_assets
            if a in index and index[a].get("technical_owner")
        }
    )
    contracts = {
        a: index[a].get("contract_version")
        for a in sorted(affected_assets)
        if a in index and index[a].get("contract_version")
    }
    runbooks = sorted(
        {index[a]["runbook"] for a in affected_assets if a in index and index[a].get("runbook")}
    )

    report: dict[str, Any] = {
        "asset": asset_id,
        "resolved_node": key,
        "upstream": upstream,
        "direct_downstream": direct,
        "transitive_downstream": transitive,
        "affected_tests": _affected_tests(affected_assets),
        "affected_contracts": contracts,
        "affected_consumers": sorted(affected_consumers),
        "owners_to_notify": owners,
        "runbooks": runbooks,
    }

    if change_file and change_file.exists():
        change = yaml.safe_load(change_file.read_text(encoding="utf-8")) or {}
        report["change"] = {
            "change_id": change.get("change_id"),
            "compatibility_class": change.get("compatibility_class"),
            "new_contract_version": change.get("new_contract_version"),
            "approval_reference": bool(str(change.get("approval_reference", "")).strip()),
        }

    return report


def render_summary(report: dict[str, Any]) -> str:
    lines = [
        f"# Impact report: {report['asset']}",
        "",
        f"- Resolved node: `{report['resolved_node']}`",
        f"- Direct downstream ({len(report['direct_downstream'])}): "
        + ", ".join(f"`{d}`" for d in report["direct_downstream"])
        or "- Direct downstream: none",
        f"- Transitive downstream ({len(report['transitive_downstream'])}): "
        + ", ".join(f"`{d}`" for d in report["transitive_downstream"]),
        f"- Affected consumers: {', '.join(report['affected_consumers']) or 'none'}",
        f"- Owners to notify: {', '.join(report['owners_to_notify']) or 'none'}",
        f"- Affected contracts: {report['affected_contracts']}",
        f"- Affected tests/props: {len(report['affected_tests'])} file(s)",
        f"- Runbooks: {', '.join(report['runbooks']) or 'none'}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atlas consumer-impact analysis")
    parser.add_argument("--asset", required=True)
    parser.add_argument("--change", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    report = analyze(args.asset, args.change)
    summary = render_summary(report)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "impact.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        (args.output_dir / "impact.md").write_text(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
