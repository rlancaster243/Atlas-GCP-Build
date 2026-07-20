"""Atlas reference-architecture validation (Sprint 8).

Validates the curated reference package and the machine-readable evidence index
against repository truth: referenced files exist, IDs are unique, live claims are
backed by live evidence, and blocked work is never presented as complete.

Import the API from :mod:`atlas.reference.validate` (kept out of package import
to avoid a runpy double-import warning under ``python -m atlas.reference.validate``).
"""
