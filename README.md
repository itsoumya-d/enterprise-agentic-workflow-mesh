# Enterprise Agentic Workflow Mesh

A resilient, forward-deployed enterprise AI agent orchestrator with stateful persistence, schema-enforced tool execution, and PII redaction middleware.

## Architecture

```
[Enterprise Events / Webhooks]
              │
              ▼
    [Agent Workflow Mesh]
    ├── PII Redaction Filter
    ├── Token Budget Governor
    ├── Schema-Enforced Tool Dispatch
    └── Stateful Session Store (Redis / Postgres)
```

## Features

- **Schema-Enforced Tool Execution**: Strict type and parameter validation prior to tool dispatch.
- **Stateful Audit & Session Store**: Transactional state persistence with replay protection.
- **PII / Secret Scrubbing**: Automatic scrubbing of card numbers, emails, and credentials before LLM ingestion.
- **Token Budget & Execution Safeguards**: Dynamic quotas preventing unbounded agentic loops.

## Testing

```bash
pytest -v
```
