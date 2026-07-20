# Atlas Reference-Architecture Package

**Status:** CURRENT · A curated *map* over the proven Atlas system. It summarizes
stable decisions and **links** to the authoritative detail (code, ADRs, runbooks,
validation reports); it does not duplicate them. Start at
[`../../START_HERE.md`](../../START_HERE.md).

## Package contents

| Document | Purpose |
| --- | --- |
| [reference-manifest.yml](reference-manifest.yml) | machine-readable index (validated by `atlas.reference.validate`) |
| [system-context.md](system-context.md) | problem, actors, boundaries, context diagram |
| [architecture-overview.md](architecture-overview.md) | data / control / operational / governance flows |
| [architecture-invariants.md](architecture-invariants.md) | properties that must remain true + enforcement |
| [component-catalog-reusable.md](component-catalog-reusable.md) | reusable-candidate components (RC-01..22) |
| [component-catalog-atlas-specific.md](component-catalog-atlas-specific.md) | project-specific components (AC-01..13) |
| [interfaces-and-contracts.md](interfaces-and-contracts.md) | stable boundaries + enforcement |
| [extension-points.md](extension-points.md) | how to extend safely |
| [operating-model.md](operating-model.md) | ownership + authority + cadence |
| [security-and-identity-model.md](security-and-identity-model.md) | identities, WIF, least-privilege status |
| [reliability-and-recovery-model.md](reliability-and-recovery-model.md) | detect→…→prevent, replay, rollback |
| [observability-model.md](observability-model.md) | audit, logs, metrics, alerts, limitations |
| [cost-and-lifecycle-model.md](cost-and-lifecycle-model.md) | cost controls, retention, proven vs not |
| [evidence-index.md](evidence-index.md) | claim→evidence map (human view) |
| [capability-evidence-map.md](capability-evidence-map.md) | competency domains + honest framing |
| [unresolved-risks.md](unresolved-risks.md) | risk register + Sprint 7 blocked-gate disposition |

## Rules this package follows

- Summarize stable decisions; link to detailed sources.
- Distinguish implementation from proposal, static from live, current from
  historical, and always expose limitations.
- Never claim reusable-template status (Atlas is a reference architecture).

## Validate the package

```bash
python -m atlas.reference.validate
bash scripts/validate_ci.sh --mode static   # gate_reference_handoff
```
