"""Rollback schema-compatibility decisions (Sprint 6, ADR-015 / ADR-010).

Rule: runtime rollback to a prior release is allowed only when that release is
compatible with the currently applied schema. With additive-only migrations
that is normally true; a migration flagged ``breaking`` in
``sql/migrations/manifest.txt`` marks the boundary after which releases built
before it can no longer run. Rolling back across a breaking migration is
blocked — the operator gets forward-recovery guidance instead, and nothing is
ever reversed automatically.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.ops.migrations import Migration


@dataclass(frozen=True)
class RollbackDecision:
    """Outcome of one rollback eligibility evaluation."""

    eligible: bool
    reason: str
    blocking_migrations: tuple[str, ...] = ()


def evaluate_rollback_compatibility(
    *,
    applied_migration_ids: list[str],
    target_release_migration_ids: list[str],
    manifest: list[Migration],
) -> RollbackDecision:
    """Decide whether a prior release may be restored against the live schema.

    - Migrations pending for the target release block promotion (unchanged
      Sprint 4 rule; handled by the caller as PENDING_MIGRATIONS).
    - Applied migrations the target release does not know about are tolerated
      when additive, and block the rollback when flagged breaking.
    """
    known_to_target = set(target_release_migration_ids)
    breaking_by_id = {m.migration_id: m.breaking for m in manifest}

    newer_applied = [m for m in applied_migration_ids if m not in known_to_target]
    blocking = tuple(m for m in newer_applied if breaking_by_id.get(m, False))
    if blocking:
        return RollbackDecision(
            eligible=False,
            reason=(
                "applied schema contains breaking migration(s) the target release "
                f"predates: {list(blocking)}. Runtime rollback is blocked; recover "
                "forward (fix on a new release) instead. Breaking BigQuery "
                "migrations are never reversed automatically (ADR-010/ADR-015)."
            ),
            blocking_migrations=blocking,
        )
    unknown = [m for m in newer_applied if m not in breaking_by_id]
    if unknown:
        return RollbackDecision(
            eligible=False,
            reason=(
                f"applied migration(s) {unknown} are not in the current repository "
                "manifest, so their compatibility cannot be classified. Refusing "
                "rollback rather than guessing."
            ),
            blocking_migrations=tuple(unknown),
        )
    return RollbackDecision(
        eligible=True,
        reason=(
            "target release is schema-compatible: every newer applied migration "
            f"({newer_applied or 'none'}) is additive"
        ),
    )
