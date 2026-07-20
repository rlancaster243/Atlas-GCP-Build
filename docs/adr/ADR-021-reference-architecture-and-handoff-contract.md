# ADR-021: Reference-Architecture and Handoff Contract

- **Status:** Accepted (Sprint 8)
- **Date:** 2026-07-19
- **Deciders:** data architect, release owner
- **Related:** ADR-016 (governance source of truth), ADR-017 (schema
  compatibility), all Sprint 1–7 ADRs (the decisions this package curates)

## Context

Through Sprint 7, Atlas was understood primarily by its builder and development
agents. Knowledge lived across 61 docs, 20 ADRs, and validation reports, but
there was no single enforceable contract that (a) routes a newcomer to
authoritative sources, (b) links every major claim to evidence with a live/
static/blocked distinction, and (c) fails CI when documentation drifts from
repository truth or depends on hidden context. A repository is not transferable
merely because it contains many Markdown files.

## Decision

Establish a **reference-architecture and handoff contract** as a first-class,
CI-enforced artifact set:

1. **`START_HERE.md`** is the canonical entry point and router (not a second
   README).
2. **`docs/reference-architecture/`** is a curated *map* over existing evidence —
   it links to detailed sources and never duplicates full runbooks/reports.
3. A machine-readable **`reference-manifest.yml`** and **evidence-index.json**
   are validated by **`python -m atlas.reference.validate`**: referenced files
   exist, ids are unique, LIVE claims are backed by live evidence, blocked work
   is never marked complete, and verification commits are present.
4. A single focused CI gate, **`gate_reference_handoff`**, wired into the existing
   `validate_ci.sh` python group (no workflow YAML logic duplication), enforces
   the contract plus: no absolute local paths or prior-conversation dependencies
   in current onboarding docs, capability limitations present, public-extraction
   manifest valid, and that `atlas-sprint-8-complete` is not claimed before it
   exists.
5. **Reproducibility is tested, not asserted:** `validate_clean_clone.sh` runs
   from a fresh directory + fresh venv, and an independent handoff test scores a
   separate agent against a rubric.
6. **Reference architecture ≠ template.** Atlas is a reference architecture; the
   template-extraction plan is documented but not executed, and no template
   status is claimed.

## Consequences

- **Positive:** documentation cannot silently drift from code (CI fails);
  newcomers and agents have a single, tested entry path; claims are auditable;
  blocked work stays visibly blocked.
- **Cost:** one new gate + validator to maintain; the manifest/evidence index
  must be updated when docs/claims change (enforced, so drift is caught).
- **Boundary:** the contract governs Sprint 8 reference artifacts; it does not
  reopen Sprint 1–7 tags or change existing architecture.

## Invariants introduced

INV-R1..R5 in
[architecture-invariants.md](../reference-architecture/architecture-invariants.md):
instructions independent of prior conversations; documents identify their
verification commit; claims link to evidence; blocked work stays blocked;
reference architecture must not claim template status.
