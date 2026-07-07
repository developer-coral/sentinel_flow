# Sentinel Flow Architecture

## Purpose

Sentinel Flow is a proof-of-concept document orchestration engine. It receives unstructured documents, extracts structured business data with an AI model, routes the result based on risk and recommended action, and triggers downstream CRM/email/task workflows.

## Local PoC

```mermaid
flowchart LR
    A[Client Portal<br/>HTML Upload UI] --> B[n8n Webhook]
    B --> C[Python Extractor API<br/>FastAPI]
    C --> D[OpenRouter / Anthropic<br/>Claude-compatible model]
    D --> C
    C --> E[n8n Normalize Step]
    E --> F{Risk / Route Switch}
    F -->|High Risk| G[SMTP Sandbox Email]
    F -->|CRM Update| H[HubSpot / Attio API Action]
    F -->|Default| I[General Review Response]
    G --> J[n8n Execution Logs]
    H --> J
    I --> J
    J --> K[Postgres-backed n8n DB]
```

## Production Blueprint

```mermaid
flowchart TB
    U[Users / Internal Apps] --> ALB[AWS ALB + WAF]
    ALB --> ECS1[ECS Service: n8n Web]
    ECS1 --> SQS[SQS / Redis Queue]
    SQS --> ECS2[ECS Service: n8n Workers]
    ECS2 --> EXT[ECS Service: Extractor API]
    EXT --> AI[Anthropic / OpenRouter]
    ECS2 --> RDS[(RDS Postgres)]
    ECS2 --> CRM[Attio / HubSpot CRM]
    ECS2 --> SMTP[SES / SendGrid]
    ECS1 --> CW[CloudWatch Logs]
    ECS2 --> CW
    EXT --> CW
    SM[AWS Secrets Manager] --> ECS1
    SM --> ECS2
    SM --> EXT
```

## Core Logic Hierarchy

1. **Ingestion Layer**
   - Receives text/files through n8n webhook.
   - Optionally receives documents from email, Drive, forms, or CRM events.

2. **Extraction Layer**
   - Python service extracts readable text from TXT/PDF.
   - Sends bounded prompt to Claude/OpenRouter.
   - Validates returned JSON against a strict schema.

3. **Decision Layer**
   - Normalizes model output.
   - Classifies by `risk_level` and `recommended_route`.
   - Prevents invalid downstream actions by requiring typed structured data.

4. **Action Layer**
   - Sends review email for high-risk documents.
   - Creates/updates CRM records for safe business documents.
   - Logs execution result for auditability.

5. **Enterprise Layer**
   - Secrets managed outside code.
   - Execution history retained.
   - Logs shipped to CloudWatch.
   - Queues and workers scale independently.
   - CI/CD validates and packages every change.
