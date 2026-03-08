# Billing Service

SQS consumer + Stripe integration.

- `consumer.py` — SQS 用量消费
- `aggregator.py` — 用量聚合（按租户/Agent/模型/时间）
- `quota.py` — 配额检查
