# Public-Repository Extraction Review

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
