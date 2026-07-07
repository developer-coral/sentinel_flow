# CI/CD Blueprint

## Local Quality Gates

- Build Docker images.
- Run extractor unit tests / smoke test.
- Validate workflow JSON syntax.
- Package release artifact.

## GitHub Actions Pipeline

The included `.github/workflows/ci.yml` performs:

1. Checkout source.
2. Set up Python.
3. Install extractor dependencies.
4. Run syntax checks.
5. Validate n8n workflow JSON.
6. Build Docker Compose stack.

## Production Deployment Model

Recommended production route:

1. Merge to `main`.
2. GitHub Actions builds Docker images.
3. Images pushed to ECR.
4. Terraform applies ECS/RDS/Secrets changes.
5. n8n workflow imported or updated through controlled deployment process.
6. Smoke test calls health endpoints and test webhook.
7. Rollback by redeploying previous image tag and workflow JSON revision.
