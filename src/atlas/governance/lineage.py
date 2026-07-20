"""Repository-artifact lineage for Atlas (Sprint 7, Phase 5).

Builds a source-to-mart lineage graph WITHOUT a graph database or metadata
service — it parses the dbt model SQL for ``ref()``/``source()`` edges, the
source registry, and the governance consumer registry. Offline and
credentialless so it runs in CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from atlas.config.settings import atlas_root
from atlas.governance.registry import load_consumers

_REF_RE = re.compile(r"\bref\(\s*['\"]([^'\"]+)['\"]\s*\)")
_SOURCE_RE = re.compile(r"\bsource\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)")


@dataclass
class LineageGraph:
    upstream: dict[str, set[str]] = field(default_factory=dict)
    downstream: dict[str, set[str]] = field(default_factory=dict)
    node_types: dict[str, str] = field(default_factory=dict)

    def add_edge(self, src: str, dst: str) -> None:
        self.upstream.setdefault(dst, set()).add(src)
        self.downstream.setdefault(src, set()).add(dst)
        self.upstream.setdefault(src, set())
        self.downstream.setdefault(dst, set())

    def add_node(self, node: str, node_type: str) -> None:
        self.node_types.setdefault(node, node_type)
        self.upstream.setdefault(node, set())
        self.downstream.setdefault(node, set())

    def transitive_downstream(self, node: str) -> set[str]:
        seen: set[str] = set()
        stack = list(self.downstream.get(node, set()))
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(self.downstream.get(n, set()))
        return seen

    def transitive_upstream(self, node: str) -> set[str]:
        seen: set[str] = set()
        stack = list(self.upstream.get(node, set()))
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(self.upstream.get(n, set()))
        return seen


def _models_dir() -> Path:
    return atlas_root() / "dbt" / "atlas_dbt" / "models"


@lru_cache(maxsize=1)
def build_lineage() -> LineageGraph:
    graph = LineageGraph()

    # dbt sources -> nodes (e.g. source('atlas_raw','events') == atlas_raw.events).
    sources_yml = _models_dir() / "sources" / "sources.yml"
    if sources_yml.exists():
        data = yaml.safe_load(sources_yml.read_text(encoding="utf-8")) or {}
        for src in data.get("sources", []) or []:
            for tbl in src.get("tables", []) or []:
                node = f"{src['name']}.{tbl['name']}"
                graph.add_node(node, "source")

    # dbt models: parse ref()/source() edges from the SQL.
    for sql in sorted(_models_dir().glob("*/*.sql")):
        model = sql.stem
        layer = sql.parent.name
        graph.add_node(model, f"{layer}_model")
        text = sql.read_text(encoding="utf-8")
        for upstream in _REF_RE.findall(text):
            graph.add_node(upstream, "model_or_seed")
            graph.add_edge(upstream, model)
        for src_name, tbl in _SOURCE_RE.findall(text):
            node = f"{src_name}.{tbl}"
            graph.add_node(node, "source")
            graph.add_edge(node, model)

    # Governance consumers -> downstream consumer nodes reading governed assets.
    for consumer, spec in load_consumers().items():
        graph.add_node(consumer, f"consumer:{spec.get('type', 'unknown')}")
        for asset in spec.get("reads", []) or []:
            # Consumers may read by dbt name or fully-qualified id; normalize the
            # trailing name so 'core.fct_events' links to model 'fct_events'.
            candidates = {asset, asset.split(".")[-1]}
            linked = candidates & set(graph.node_types)
            targets = linked or {asset}
            for target in targets:
                graph.add_node(target, graph.node_types.get(target, "asset"))
                graph.add_edge(target, consumer)

    return graph


def to_dict(graph: LineageGraph) -> dict[str, object]:
    return {
        "nodes": [
            {
                "id": node,
                "type": graph.node_types.get(node, "unknown"),
                "upstream": sorted(graph.upstream.get(node, set())),
                "downstream": sorted(graph.downstream.get(node, set())),
            }
            for node in sorted(graph.node_types)
        ],
        "edge_count": sum(len(v) for v in graph.downstream.values()),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Atlas repository lineage")
    parser.add_argument("--output", type=Path, help="write machine-readable lineage JSON")
    args = parser.parse_args(argv)

    graph = build_lineage()
    payload = to_dict(graph)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
