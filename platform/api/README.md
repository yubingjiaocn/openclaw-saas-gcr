# Management API

FastAPI-based control plane for OpenClaw SaaS.

## Modules

- `routers/` — API endpoints (auth, tenants, agents, channels, usage, billing)
- `services/` — Business logic (K8s client, JWT, channel config, Stripe, usage)
- `models/` — Data models (user, tenant, agent)
- `templates/` — K8s resource templates (namespace, quota, network policy)

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- PyJWT + bcrypt (自建认证)
- kubernetes client (K8s API)
- SQLAlchemy + asyncpg (PostgreSQL)
- boto3 (AWS SQS)

## Run

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload
```
