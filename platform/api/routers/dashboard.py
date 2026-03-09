"""Dashboard aggregation endpoints — reduce multiple API round-trips to one."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.agent import Agent
from api.models.tenant import (
    Tenant, TenantResponse, TenantMember, TenantAllowedEmail,
    MemberResponse, AllowedEmailResponse,
)
from api.models.user import User
from api.services.auth_svc import get_current_user
from api.routers.tenants import get_user_tenant

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated dashboard: tenant list + admin stats (if admin). Replaces 2 API calls."""
    from api.routers.tenants import list_tenants, platform_overview

    tenants = await list_tenants(current_user, db)

    admin_stats = None
    if getattr(current_user, 'is_platform_admin', False):
        try:
            admin_stats = await platform_overview(current_user, db)
        except Exception:
            pass

    return {
        "tenants": tenants,
        "admin_stats": admin_stats,
    }


@router.get("/tenants/{tenant_name}/dashboard")
async def get_tenant_dashboard(
    tenant_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated tenant detail: info + agents + members + billing + allowed emails.
    Replaces 4-5 separate API calls with one."""
    tenant, role = await get_user_tenant(tenant_name, current_user, db)

    # --- Tenant info ---
    tenant_info = {
        "id": tenant.id,
        "name": tenant.name,
        "plan": tenant.plan,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }

    # --- Agents with status ---
    agent_result = await db.execute(
        select(Agent).where(Agent.tenant_id == tenant.id)
    )
    agents_list = []
    for a in agent_result.scalars().all():
        agents_list.append({
            "id": a.id,
            "name": a.name,
            "llm_provider": a.llm_provider,
            "llm_model": a.llm_model,
            "status": a.status,
            "channels": a.channels or [],
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    # --- Members ---
    owner_result = await db.execute(select(User).where(User.id == tenant.owner_id))
    owner = owner_result.scalar_one_or_none()

    members_list = []
    if owner:
        members_list.append({
            "user_id": owner.id,
            "email": owner.email,
            "display_name": owner.display_name,
            "role": "owner",
            "joined_at": tenant.created_at.isoformat() if tenant.created_at else None,
        })

    mem_result = await db.execute(
        select(TenantMember, User)
        .join(User, User.id == TenantMember.user_id)
        .where(TenantMember.tenant_id == tenant.id)
    )
    for membership, user in mem_result.all():
        members_list.append({
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": membership.role,
            "joined_at": membership.created_at.isoformat() if membership.created_at else None,
        })

    # --- Billing ---
    from api.routers.billing import PLAN_LIMITS
    plan_limits = PLAN_LIMITS.get(tenant.plan, PLAN_LIMITS["free"])

    # Token usage this month
    usage_result = await db.execute(text("""
        SELECT COALESCE(SUM(total_tokens), 0) as total_tokens,
               COALESCE(SUM(call_count), 0) as total_calls,
               COALESCE(SUM(estimated_cost), 0) as total_cost
        FROM daily_usage
        WHERE tenant = :tenant AND date >= date_trunc('month', CURRENT_DATE)
    """), {"tenant": tenant_name})
    usage_row = usage_result.first()

    billing_info = {
        "plan": tenant.plan,
        "limits": plan_limits,
        "current_month": {
            "total_tokens": int(usage_row.total_tokens) if usage_row else 0,
            "total_calls": int(usage_row.total_calls) if usage_row else 0,
            "estimated_cost": round(float(usage_row.total_cost), 4) if usage_row else 0,
        },
        "agent_count": len(agents_list),
        "max_agents": plan_limits.get("max_agents"),
    }

    # --- Allowed emails (admin+ only) ---
    allowed_emails = []
    if role in ("owner", "admin") or getattr(current_user, 'is_platform_admin', False):
        ae_result = await db.execute(
            select(TenantAllowedEmail)
            .where(TenantAllowedEmail.tenant_id == tenant.id)
            .order_by(TenantAllowedEmail.created_at.desc())
        )
        for e in ae_result.scalars().all():
            allowed_emails.append({
                "id": e.id,
                "email": e.email,
                "role": e.role,
                "used": e.used,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            })

    return {
        "tenant": tenant_info,
        "role": role,
        "agents": agents_list,
        "members": members_list,
        "billing": billing_info,
        "allowed_emails": allowed_emails,
    }
