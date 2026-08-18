"""Stripe billing — subscription tiers and webhook processing."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grc_dashboard.api.tenant_context import get_tenant_id
from grc_dashboard.auth.dependencies import RequireAdmin
from grc_dashboard.billing.entitlements import (
    entitlements_summary,
    stripe_required_for_checkout,
)
from grc_dashboard.db.models import BillingWebhookEvent, Tenant, User
from grc_dashboard.db.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()

PLANS = {
    "starter": {"name": "Starter", "price_usd": 499, "seats": 10, "frameworks": 2},
    "growth": {"name": "Growth", "price_usd": 1299, "seats": 50, "frameworks": 5},
    "enterprise": {"name": "Enterprise", "price_usd": 2999, "seats": 500, "frameworks": 99},
}


class CheckoutRequest(BaseModel):
    plan: str = "growth"


@router.get("/plans")
async def list_plans(current_user: User = RequireAdmin) -> dict[str, Any]:
    return {"plans": PLANS, "currency": "usd", "billing": "monthly"}


@router.get("/entitlements")
async def get_entitlements(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    from sqlalchemy import func

    tenant_id = get_tenant_id(request)
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    seat_res = await db.execute(
        select(func.count()).select_from(User).where(User.tenant_id == tenant_id, User.is_active.is_(True))
    )
    seats = int(seat_res.scalar() or 0)
    from grc_dashboard.db.models import IntegrationSettings

    int_res = await db.execute(
        select(IntegrationSettings).where(IntegrationSettings.tenant_id == tenant_id)
    )
    settings = int_res.scalar_one_or_none()
    connected = dict(settings.connected_integrations or {}) if settings else {}
    integration_count = len([k for k, v in connected.items() if v.get("status") == "connected"])
    return entitlements_summary(tenant, seats, integration_count)


@router.get("/subscription")
async def get_subscription(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    tenant_id = get_tenant_id(request)
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "tenant_id": tenant_id,
        "plan": tenant.plan,
        "subscription_status": tenant.subscription_status,
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
    }


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User = RequireAdmin,
) -> dict[str, Any]:
    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")
    tenant_id = get_tenant_id(request)
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not stripe_key:
        if stripe_required_for_checkout():
            raise HTTPException(
                status_code=503,
                detail="STRIPE_SECRET_KEY required in production. Demo billing is disabled.",
            )
        tenant = await db.get(Tenant, tenant_id)
        if tenant:
            tenant.plan = body.plan
            tenant.subscription_status = "active_demo"
            await db.commit()
        return {
            "mode": "demo",
            "message": f"Plan upgraded to {body.plan} (demo — set STRIPE_SECRET_KEY for live billing)",
            "plan": body.plan,
        }

    try:
        import stripe

        stripe.api_key = stripe_key
        price_id = os.getenv(f"STRIPE_PRICE_{body.plan.upper()}", "")
        if not price_id:
            raise HTTPException(
                status_code=400,
                detail=f"Set STRIPE_PRICE_{body.plan.upper()} env var",
            )
        base_url = os.getenv("VALENCE_PUBLIC_URL", "http://localhost:8000")
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}/?billing=success",
            cancel_url=f"{base_url}/?billing=cancel",
            metadata={"tenant_id": tenant_id, "plan": body.plan},
        )
        return {"mode": "stripe", "checkout_url": session.url, "session_id": session.id}
    except ImportError:
        raise HTTPException(status_code=501, detail="Install stripe package for live billing") from None
    except Exception as exc:
        logger.warning("stripe_checkout_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="Stripe checkout failed") from exc


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    """Handle Stripe subscription lifecycle events.

    In production set STRIPE_WEBHOOK_SECRET. Without it, events are accepted for
    local/demo testing only.
    """
    payload = await request.body()
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

    event: dict[str, Any]
    if stripe_key:
        try:
            import stripe

            stripe.api_key = stripe_key
            if webhook_secret:
                if not stripe_signature:
                    raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
                evt = stripe.Webhook.construct_event(
                    payload=payload,
                    sig_header=stripe_signature,
                    secret=webhook_secret,
                )
                event = dict(evt)
            else:
                # SECURITY: Stripe key is set but no webhook secret — block in production
                from grc_dashboard.deployment.production import IS_PRODUCTION

                if IS_PRODUCTION:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "STRIPE_WEBHOOK_SECRET must be set when STRIPE_SECRET_KEY is configured. "
                            "Unsigned webhook payloads are not accepted in production."
                        ),
                    )
                logger.warning(
                    "stripe_webhook_unverified",
                    message="Accepting unverified webhook in development — set STRIPE_WEBHOOK_SECRET",
                )
                event = json.loads(payload.decode("utf-8"))
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("stripe_webhook_invalid", error=str(exc))
            raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
    else:
        # Demo mode without Stripe credentials — development only.
        from grc_dashboard.deployment.production import IS_PRODUCTION

        if IS_PRODUCTION:
            raise HTTPException(
                status_code=503,
                detail="STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET required in production.",
            )
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid webhook JSON") from exc

    event_type = str(event.get("type", ""))
    raw_event_id = str(event.get("id") or "")
    payload_hash = __import__("hashlib").sha256(payload).hexdigest()
    event_id = raw_event_id or f"stripe:{event_type}:{payload_hash[:24]}"

    existing = await db.execute(
        select(BillingWebhookEvent).where(BillingWebhookEvent.event_id == event_id)
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "event_id": event_id}

    evt_row = BillingWebhookEvent(
        provider="stripe",
        event_id=event_id,
        event_type=event_type,
        payload_hash=payload_hash,
        processed=False,
    )
    db.add(evt_row)
    await db.flush()

    obj = ((event.get("data") or {}).get("object") or {})
    metadata = obj.get("metadata") or {}

    tenant_id = metadata.get("tenant_id")
    if not tenant_id:
        customer_id = obj.get("customer")
        if customer_id:
            res = await db.execute(select(Tenant).where(Tenant.stripe_customer_id == str(customer_id)))
            tenant = res.scalar_one_or_none()
            tenant_id = tenant.id if tenant else None

    if not tenant_id:
        logger.info("stripe_webhook_ignored", reason="tenant_not_found", event_type=event_type)
        evt_row.processed = True
        evt_row.processed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "ignored", "reason": "tenant_not_found", "event_id": event_id}

    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        evt_row.processed = True
        evt_row.processed_at = datetime.now(UTC)
        await db.commit()
        return {"status": "ignored", "reason": "tenant_not_found", "event_id": event_id}

    if event_type in {"checkout.session.completed", "customer.subscription.created", "customer.subscription.updated"}:
        tenant.plan = metadata.get("plan") or tenant.plan or "growth"
        tenant.subscription_status = "active"
        tenant.stripe_customer_id = str(obj.get("customer") or tenant.stripe_customer_id or "")
        tenant.stripe_subscription_id = str(obj.get("subscription") or obj.get("id") or tenant.stripe_subscription_id or "")
    elif event_type in {"customer.subscription.deleted"}:
        tenant.subscription_status = "cancelled"
    elif event_type in {"invoice.payment_failed"}:
        tenant.subscription_status = "past_due"

    evt_row.processed = True
    evt_row.processed_at = datetime.now(UTC)
    await db.commit()
    return {"status": "ok", "event_type": event_type, "tenant_id": tenant_id, "event_id": event_id}
