# Security Plan

## Secrets

- No API keys are committed to source control.
- Local development uses `.env` copied from `.env.example`.
- Production uses AWS Secrets Manager or equivalent.
- n8n credentials should be stored in n8n's encrypted credential store.
- `N8N_ENCRYPTION_KEY` must be stable and randomly generated before credential creation.

## Data Handling

- Uploaded documents are processed in memory by the extractor service.
- The PoC does not persist raw files by default.
- n8n execution logs may contain structured results and should be treated as sensitive.
- Production should enable log redaction for fields containing PII, legal text, financial data, and secrets.

## Authentication and Authorization

Local PoC:
- Intended for local demonstration only.
- n8n should not be exposed to the public internet without authentication.

Production:
- Put n8n behind SSO or VPN.
- Restrict webhook endpoints using signed tokens or HMAC validation.
- Separate operator, developer, and auditor permissions.

## Network Controls

Production:
- Public access only through ALB + WAF.
- n8n workers, extractor, and Postgres run in private subnets.
- Outbound API access restricted by security group and egress policy.

## Auditability

- n8n execution history records every step, timestamp, input, output, and error.
- Production logs should be shipped to CloudWatch or another SIEM.
- Workflow JSON is version-controlled for change history.

## Failure Handling

- AI errors fail closed: no CRM/email action is taken if schema validation fails.
- High-risk or uncertain documents route to human review.
- Retry policies should be configured for transient API failures only.
