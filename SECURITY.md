# Security Policy

Do not commit credentials, service-account keys, API keys, OAuth secrets, webhook
URLs, personal notification addresses, or production data.

Use Workload Identity Federation for GitHub-to-GCP authentication. Keep pull
request CI credentialless. Apply least privilege, plan IAM changes before
mutation, and review the security and identity documentation before deployment.

Report security issues privately to the repository owner rather than opening a
public issue containing exploit details or credentials.
