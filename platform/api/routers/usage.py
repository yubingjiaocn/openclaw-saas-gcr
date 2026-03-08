"""Usage API - agent usage and metrics"""
import sys
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.agent import Agent
from api.models.tenant import Tenant
from api.models.user import User
from api.services.auth_svc import get_current_user
from api.routers.tenants import get_user_tenant
from api.services.k8s_client import k8s_client

# Import billing models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from billing.models import DailyUsage, HourlyUsage  # noqa: E402

router = APIRouter(tags=["usage"])


@router.get("/api/v1/tenants/{tenant_name}/usage")
async def get_tenant_usage(
    tenant_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage summary for a tenant"""
    tenant, _role = await get_user_tenant(tenant_name, current_user, db)

    # Get all agents
    result = await db.execute(select(Agent).where(Agent.tenant_id == tenant.id))
    agents = result.scalars().all()

    agent_usage = []
    for agent in agents:
        try:
            pod_status = await k8s_client.get_pod_status(tenant_name, agent.name)
            instance = await k8s_client.get_openclaw_instance(tenant_name, agent.name)
            crd_phase = instance.get("status", {}).get("phase", "Unknown") if instance else "NotFound"

            agent_usage.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "status": agent.status,
                "crd_phase": crd_phase,
                "channels": agent.channels,
                "pod_phase": pod_status.get("phase"),
                "pod_restarts": sum(
                    c.get("restart_count", 0) for c in pod_status.get("containers", [])
                ) if pod_status.get("containers") else 0,
                "pod_start_time": pod_status.get("start_time"),
            })
        except Exception:
            agent_usage.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "status": agent.status,
                "crd_phase": "Error",
                "channels": agent.channels,
                "pod_phase": None,
                "pod_restarts": 0,
                "pod_start_time": None,
            })

    return {
        "tenant": tenant_name,
        "plan": tenant.plan,
        "agent_count": len(agents),
        "agents": agent_usage,
    }


@router.get("/api/v1/tenants/{tenant_name}/usage/tokens")
async def get_tenant_token_usage(
    tenant_name: str,
    days: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed token usage for a tenant over specified time period"""
    # Verify tenant ownership
    tenant, _role = await get_user_tenant(tenant_name, current_user, db)

    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Get daily usage
    result = await db.execute(
        select(DailyUsage)
        .where(
            DailyUsage.tenant == tenant_name,
            DailyUsage.date >= start_date,
            DailyUsage.date <= end_date,
        )
        .order_by(DailyUsage.date.desc())
    )
    daily_records = result.scalars().all()

    # Calculate totals
    total_tokens = sum(r.total_tokens for r in daily_records)
    total_input = sum(r.input_tokens for r in daily_records)
    total_output = sum(r.output_tokens for r in daily_records)
    total_cache_read = sum(r.cache_read for r in daily_records)
    total_cache_write = sum(r.cache_write for r in daily_records)
    total_calls = sum(r.call_count for r in daily_records)
    total_cost = sum(r.estimated_cost for r in daily_records)

    # Group by agent
    agent_breakdown = {}
    for record in daily_records:
        if record.agent not in agent_breakdown:
            agent_breakdown[record.agent] = {
                "agent_name": record.agent,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_write": 0,
                "call_count": 0,
                "estimated_cost": 0.0,
            }
        agent_breakdown[record.agent]["total_tokens"] += record.total_tokens
        agent_breakdown[record.agent]["input_tokens"] += record.input_tokens
        agent_breakdown[record.agent]["output_tokens"] += record.output_tokens
        agent_breakdown[record.agent]["cache_read"] += record.cache_read
        agent_breakdown[record.agent]["cache_write"] += record.cache_write
        agent_breakdown[record.agent]["call_count"] += record.call_count
        agent_breakdown[record.agent]["estimated_cost"] += record.estimated_cost

    # Group by model
    model_breakdown = {}
    for record in daily_records:
        model_key = f"{record.provider}:{record.model}"
        if model_key not in model_breakdown:
            model_breakdown[model_key] = {
                "provider": record.provider,
                "model": record.model,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "call_count": 0,
                "estimated_cost": 0.0,
            }
        model_breakdown[model_key]["total_tokens"] += record.total_tokens
        model_breakdown[model_key]["input_tokens"] += record.input_tokens
        model_breakdown[model_key]["output_tokens"] += record.output_tokens
        model_breakdown[model_key]["call_count"] += record.call_count
        model_breakdown[model_key]["estimated_cost"] += record.estimated_cost

    # Daily time series
    daily_series = [
        {
            "date": record.date.isoformat(),
            "agent": record.agent,
            "model": record.model,
            "provider": record.provider,
            "total_tokens": record.total_tokens,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "cache_read": record.cache_read,
            "cache_write": record.cache_write,
            "call_count": record.call_count,
            "estimated_cost": record.estimated_cost,
        }
        for record in daily_records
    ]

    return {
        "tenant": tenant_name,
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "summary": {
            "total_tokens": total_tokens,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cache_read,
            "cache_write_tokens": total_cache_write,
            "total_calls": total_calls,
            "estimated_cost": round(total_cost, 2),
        },
        "by_agent": list(agent_breakdown.values()),
        "by_model": list(model_breakdown.values()),
        "daily": daily_series,
    }


@router.get("/api/v1/tenants/{tenant_name}/agents/{agent_name}/usage")
async def get_agent_token_usage(
    tenant_name: str,
    agent_name: str,
    hours: int = Query(default=24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed hourly token usage for a specific agent"""
    # Verify tenant and agent ownership
    tenant, _role = await get_user_tenant(tenant_name, current_user, db)

    result = await db.execute(
        select(Agent).where(Agent.tenant_id == tenant.id, Agent.name == agent_name)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    # Get hourly usage
    result = await db.execute(
        select(HourlyUsage)
        .where(
            HourlyUsage.tenant == tenant_name,
            HourlyUsage.agent == agent_name,
            HourlyUsage.hour >= start_time,
            HourlyUsage.hour <= end_time,
        )
        .order_by(HourlyUsage.hour.desc())
    )
    hourly_records = result.scalars().all()

    # Calculate totals
    total_tokens = sum(r.total_tokens for r in hourly_records)
    total_input = sum(r.input_tokens for r in hourly_records)
    total_output = sum(r.output_tokens for r in hourly_records)
    total_calls = sum(r.call_count for r in hourly_records)
    total_cost = sum(r.estimated_cost for r in hourly_records)

    # Hourly time series
    hourly_series = [
        {
            "hour": record.hour.isoformat(),
            "model": record.model,
            "provider": record.provider,
            "total_tokens": record.total_tokens,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "cache_read": record.cache_read,
            "cache_write": record.cache_write,
            "call_count": record.call_count,
            "estimated_cost": record.estimated_cost,
        }
        for record in hourly_records
    ]

    return {
        "tenant": tenant_name,
        "agent": agent_name,
        "period_hours": hours,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "summary": {
            "total_tokens": total_tokens,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "total_calls": total_calls,
            "estimated_cost": round(total_cost, 2),
        },
        "hourly": hourly_series,
    }
