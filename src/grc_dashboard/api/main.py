"""VALENCE GRC Dashboard — FastAPI Application Entry Point."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from grc_dashboard.api.middleware.edge_rate_limit import edge_rate_limit_middleware
from grc_dashboard.api.pipeline_runner import PipelineRunner
from grc_dashboard.api.routers import (
    audit_log,
    auditor,
    auditor_marketplace,
    auth,
    benchmarking,
    billing,
    boarddeck,
    breach_simulation,
    cascade,
    chatops,
    command_center,
    competitor_import,
    compliance,
    connectors,
    control_monitoring,
    devices,
    evidence,
    evidence_export,
    evidence_requests,
    findings,
    integrations_hub,
    intelligence,
    itsm,
    maturity,
    metrics,
    msp,
    notifications,
    oauth_integrations,
    pentest,
    personnel,
    policies,
    questionnaires,
    remediation,
    reports,
    risk,
    risk_treatment,
    scim,
    search,
    tenants,
    threat_intel,
    timeline,
    training,
    trust_center,
    users,
    vendors,
    whatif,
    workflows,
    ws,
)
from grc_dashboard.auth.jwt_handler import decode_token
from grc_dashboard.db.session import engine, init_db
from grc_dashboard.deployment.production import collect_readiness, validate_production_startup
from grc_dashboard.tenancy.constants import DEMO_TENANT_IDS, normalize_tenant_id
from grc_dashboard.tenancy.demo_scenarios import build_tenant_metrics
from grc_dashboard.tenancy.service import resolve_tenant_for_request

logger = structlog.get_logger(__name__)

_PUBLIC_PREFIXES = (
    "/api/health",
    "/api/status",
    "/api/auth",
    "/api/tenants/demo",
    "/api/tenants/register",
    "/api/trust-center/public",
    "/api/integrations/oauth/callback",
    "/api/chatops/slack",
    "/api/chatops/teams",
    "/api/scim/",
    "/trust",
    "/static",
    "/ws",
)



@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Startup: init DB, seed demo sandboxes, run pipeline for production tenants."""
    validate_production_startup()
    logger.info("valence_api_starting")
    await init_db()

    runner = PipelineRunner()
    app.state.pipeline_runner = runner
    app.state.latest_results_by_tenant = {}
    app.state.last_run_at = ""
    app.state.last_run_id = ""
    app.state.websocket_clients = {}

    for tenant_id in DEMO_TENANT_IDS:
        app.state.latest_results_by_tenant[tenant_id] = build_tenant_metrics(tenant_id)

    from grc_dashboard.pipeline.tenant_runner import discover_production_tenant_ids
    from grc_dashboard.tenancy.demo_scenarios import build_pipeline_error_state

    for tid in await discover_production_tenant_ids():
        app.state.latest_results_by_tenant[tid] = build_pipeline_error_state(
            tid, "VALENCE_STARTUP", "Connect SIEM or upload logs to load metrics"
        )

    skip_schedulers = os.getenv("VALENCE_SKIP_PIPELINE_SCHEDULER", "").lower() in {"1", "true", "yes"}

    if not skip_schedulers:
        asyncio.create_task(runner.run_once(app.state))
        task = asyncio.create_task(runner.run_scheduled(app.state, interval_seconds=300))
        app.state.scheduler_task = task
    else:
        app.state.scheduler_task = None

    from grc_dashboard.rendering.report_scheduler import run_report_scheduler

    if not skip_schedulers:
        report_task = asyncio.create_task(run_report_scheduler(app.state, interval_seconds=3600))
        app.state.report_scheduler_task = report_task
    else:
        app.state.report_scheduler_task = None

    logger.info("valence_api_ready")

    pid_file = os.getenv("VALENCE_PID_FILE", "").strip()
    if pid_file:
        try:
            Path(pid_file).write_text(str(os.getpid()), encoding="utf-8")
        except OSError as exc:
            logger.warning("pid_file_write_failed", path=pid_file, error=str(exc))

    yield

    if pid_file:
        try:
            Path(pid_file).unlink(missing_ok=True)
        except OSError:
            pass

    if app.state.scheduler_task:
        app.state.scheduler_task.cancel()
        try:
            await app.state.scheduler_task
        except asyncio.CancelledError:
            pass
    if app.state.report_scheduler_task:
        app.state.report_scheduler_task.cancel()
        try:
            await app.state.report_scheduler_task
        except asyncio.CancelledError:
            pass
    try:
        await engine.dispose()
    except Exception as exc:
        logger.warning("engine_dispose_failed", error=str(exc))
    logger.info("valence_api_shutdown")


app = FastAPI(
    title="VALENCE GRC Dashboard",
    description=(
        "Enterprise Security Metrics, Risk Quantification & Compliance Platform. "
        "Implements FAIR risk ontology, Monte Carlo VaR, cryptographic audit lineage, "
        "and DORA/NIS2/SOC2 framework mapping."
    ),
    version="2.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VALENCE GRC v2.1.0 — Enterprise API Documentation</title>
    <link rel="icon" type="image/png" href="/static/favicon.ico">
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <link rel="stylesheet" type="text/css" href="/static/swagger-theme.css">
</head>
<body>
    <!-- Navigation Header -->
    <div class="valence-api-header">
        <div class="valence-api-brand">
            <div class="valence-api-brand-logo">V</div>
            VALENCE <span class="valence-api-badge">API v2.1.0</span>
        </div>
        <div class="valence-quick-nav">
            <a class="valence-nav-pill" href="/dashboard/">Back to Platform</a>
            <a class="valence-nav-pill" href="/api/auth/sandbox-info" target="_blank">Sandbox Credentials</a>
            <a class="valence-nav-pill" href="/api/openapi.json" target="_blank">OpenAPI Spec (JSON)</a>
            <a class="valence-nav-pill" href="/api/redoc">ReDoc Documentation</a>
        </div>
    </div>

    <!-- Security & Sensitive Data Guidelines -->
    <div class="valence-security-banner">
        <div class="security-card">
            <div class="security-card-header">
                <div class="security-title">
                    API Security & Sensitive Data Protection
                </div>
                <span style="font-size: 0.8rem; color: #15803D; font-weight: 600; background: #DCFCE7; padding: 3px 10px; border-radius: 999px;">OWASP Compliant</span>
            </div>
            <p style="font-size: 0.875rem; color: #475569; margin: 0 0 12px 0; line-height: 1.5;">
                Follow these mandatory security rules to ensure safe API usage and protect sensitive platform data.
            </p>
            <div class="security-grid">
                <div class="security-rule">
                    <div class="security-rule-title">1. Token Authorization</div>
                    <div class="security-rule-desc">Authenticate requests using HTTP Header <code>Authorization: Bearer &lt;token&gt;</code>. Never expose API secrets in client-side code or public repositories.</div>
                </div>
                <div class="security-rule">
                    <div class="security-rule-title">2. Sensitive Data Protection</div>
                    <div class="security-rule-desc">Do not transmit cleartext passwords, unhashed PII, or confidential secrets in URL query parameters or unencrypted payloads.</div>
                </div>
                <div class="security-rule">
                    <div class="security-rule-title">3. Tenant Data Scoping</div>
                    <div class="security-rule-desc">All requests are strictly bound to tenant context via JWT claims. Unauthorized cross-tenant queries return HTTP 403 Forbidden.</div>
                </div>
                <div class="security-rule">
                    <div class="security-rule-title">4. Rate Limit & Abuse Control</div>
                    <div class="security-rule-desc">Authentication endpoints enforce a limit of 10 requests/min per IP. Repeated authentication failures trigger a 15-minute lockout.</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Category Filter Bar -->
    <div class="valence-filter-bar">
        <button class="filter-chip active" onclick="filterCategory('')">All Endpoints</button>
        <button class="filter-chip" onclick="filterCategory('Authentication')">Authentication</button>
        <button class="filter-chip" onclick="filterCategory('Tenants')">Tenants</button>
        <button class="filter-chip" onclick="filterCategory('Metrics')">Metrics & Risk</button>
        <button class="filter-chip" onclick="filterCategory('Compliance')">Compliance & DORA</button>
        <button class="filter-chip" onclick="filterCategory('Audit Findings')">Audit & Evidence</button>
        <button class="filter-chip" onclick="filterCategory('SENTINEL Vendor Risk')">Vendor Risk</button>
        <button class="filter-chip" onclick="filterCategory('AI Intelligence')">AI Intelligence</button>
        <button class="filter-chip" onclick="filterCategory('Connectors')">Connectors & SCIM</button>
    </div>

    <!-- Swagger UI Mount -->
    <div id="swagger-ui"></div>

    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {
            const ui = SwaggerUIBundle({
                url: "/api/openapi.json",
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout",
                docExpansion: "list",
                filter: true,
                defaultModelsExpandDepth: 1,
                displayRequestDuration: true
            });
            window.ui = ui;
        };

        function filterCategory(cat) {
            document.querySelectorAll('.filter-chip').forEach(btn => btn.classList.remove('active'));
            if (event && event.target) {
                event.target.classList.add('active');
            }
            
            const searchInput = document.querySelector('.swagger-ui .filter-container input');
            if (searchInput) {
                searchInput.value = cat;
                const inputEvent = new Event('input', { bubbles: true });
                searchInput.dispatchEvent(inputEvent);
            }
        }
    </script>
</body>
</html>
    """)

# Initialize OpenTelemetry instrumentation
from grc_dashboard.api.middleware.observability import setup_observability

setup_observability(app)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a unique request ID to every response for traceability."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def edge_rate_limit(request: Request, call_next):
    return await edge_rate_limit_middleware(request, call_next)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """OWASP-aligned response headers for production deployments."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # SECURITY: Removed 'unsafe-eval' from script-src. Only 'unsafe-inline' remains
    # (required by inline <script> tags in the SPA — migrate to nonces for full lockdown).
    csp = (
        "default-src 'self' ws: wss:; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com https://unpkg.com; "
        "connect-src 'self' ws: wss:; "
        "img-src 'self' data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    response.headers["Content-Security-Policy"] = csp
    if request.url.scheme == "https" or os.getenv("VALENCE_FORCE_HSTS", "false").lower() in {"1", "true", "yes"}:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """Resolve tenant from JWT + optional header; never trust X-Tenant-ID alone."""
    path = request.url.path
    if not path.startswith("/api/") or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return await call_next(request)

    jwt_tenant: str | None = None
    jwt_username: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            payload = decode_token(auth_header[7:])
            if payload.get("type") == "access":
                jwt_tenant = payload.get("tenant_id")
                jwt_username = payload.get("sub")
        except ValueError:
            pass

    requested = request.headers.get("X-Tenant-ID")
    try:
        tenant_id = resolve_tenant_for_request(
            jwt_tenant_id=jwt_tenant,
            jwt_username=jwt_username,
            requested_tenant_id=requested,
        )
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    tenant_id = normalize_tenant_id(tenant_id)
    request.state.tenant_id = tenant_id

    by_tenant: dict[str, Any] = request.app.state.latest_results_by_tenant
    if tenant_id not in by_tenant:
        from grc_dashboard.tenancy.constants import is_demo_tenant
        from grc_dashboard.tenancy.demo_scenarios import build_pipeline_error_state

        if is_demo_tenant(tenant_id):
            by_tenant[tenant_id] = build_tenant_metrics(tenant_id)
        else:
            by_tenant[tenant_id] = build_pipeline_error_state(
                tenant_id, "VALENCE_PENDING", "No metrics loaded yet for this organization"
            )

    request.state.tenant_results = by_tenant[tenant_id]

    # --- Audit Activity Logging (SOC2 requirement) ---
    if jwt_username and path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        import asyncio

        from grc_dashboard.api.routers.audit_log import record_activity

        action_map = {"POST": "create", "PUT": "update", "PATCH": "update", "DELETE": "delete"}
        resource_type = path.split("/")[2] if len(path.split("/")) > 2 else "unknown"
        asyncio.create_task(
            record_activity(
                tenant_id=tenant_id,
                username=jwt_username,
                action=action_map.get(request.method, "unknown"),
                resource_type=resource_type,
                resource_id=path,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent", "")[:500],
            )
        )

    return await call_next(request)


_cors_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,https://localhost",
).split(",")

if os.getenv("VALENCE_ENV", "development").lower() == "production":
    _parsed_cors = [o.strip() for o in _cors_origins if o.strip()]
    if not _parsed_cors:
        raise SystemExit("CORS_ALLOWED_ORIGINS must be set in production")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization", "Content-Type", "Accept", "Origin",
        "X-Requested-With", "X-Tenant-ID", "X-Request-ID",
        "Stripe-Signature", "X-VALENCE-Tenant-ID", "X-ChatOps-Secret",
    ],
)

app.include_router(auth.router,        prefix="/api/auth",        tags=["Authentication"])
app.include_router(tenants.router,     prefix="/api/tenants",     tags=["Tenants"])
app.include_router(users.router,       prefix="/api/users",       tags=["Team Access"])
app.include_router(metrics.router,     prefix="/api/metrics",     tags=["Metrics"])
app.include_router(risk.router,        prefix="/api/risk",        tags=["Risk"])
app.include_router(compliance.router,  prefix="/api/compliance",  tags=["Compliance"])
app.include_router(reports.router,     prefix="/api/reports",     tags=["Reports"])
app.include_router(connectors.router,  prefix="/api/connectors",  tags=["Connectors"])
app.include_router(findings.router,    prefix="/api/findings",    tags=["Audit Findings"])
app.include_router(ws.router,          prefix="/ws",              tags=["WebSocket"])
app.include_router(whatif.router,      prefix="/api/risk/whatif",   tags=["What-If Simulator"])
app.include_router(benchmarking.router, prefix="/api/benchmarking", tags=["Industry Benchmarking"])
app.include_router(timeline.router,    prefix="/api/timeline",     tags=["Security Timeline"])
app.include_router(threat_intel.router, prefix="/api/threat-intel", tags=["Threat Intelligence"])
app.include_router(evidence.router,    prefix="/api/evidence",     tags=["Evidence Vault"])
app.include_router(evidence_requests.router, prefix="/api/evidence", tags=["Evidence Requests"])
app.include_router(vendors.router,     prefix="/api/vendors",      tags=["SENTINEL Vendor Risk"])
app.include_router(intelligence.router, prefix="/api/intelligence", tags=["AI Intelligence"])
app.include_router(policies.router,       prefix="/api/policies",       tags=["Policy Library"])
app.include_router(auditor.router,        prefix="/api/auditor",        tags=["Auditor Portal"])
app.include_router(trust_center.router,   prefix="/api/trust-center",   tags=["Trust Center"])
app.include_router(personnel.router,      prefix="/api/personnel",      tags=["Personnel JML"])
app.include_router(devices.router,        prefix="/api/devices",        tags=["Device Compliance"])
app.include_router(questionnaires.router, prefix="/api/questionnaires", tags=["Security Questionnaires"])
app.include_router(training.router,       prefix="/api/training",       tags=["Security Training"])
app.include_router(pentest.router,        prefix="/api/pentest",        tags=["Pen Test Management"])
app.include_router(control_monitoring.router, prefix="/api/control-monitoring", tags=["Continuous Control Monitoring"])
app.include_router(remediation.router,    prefix="/api/remediation",    tags=["Remediation Tasks"])
app.include_router(itsm.router,             prefix="/api/itsm",             tags=["ITSM & CMDB"])
app.include_router(workflows.router,        prefix="/api/workflows",        tags=["Enterprise Workflows"])
app.include_router(auditor_marketplace.router, prefix="/api/auditor-marketplace", tags=["Auditor Marketplace"])
app.include_router(integrations_hub.router, prefix="/api/integrations/hub", tags=["Integration Hub"])
app.include_router(oauth_integrations.router, prefix="/api/integrations/oauth", tags=["OAuth Integrations"])
app.include_router(scim.router, prefix="/api/scim/v2", tags=["SCIM Provisioning"])
app.include_router(cascade.router,     prefix="/api/risk/cascade", tags=["Risk Cascade"])
app.include_router(boarddeck.router,   prefix="/api/board-deck",   tags=["Board Deck"])
app.include_router(search.router,           prefix="/api/search",           tags=["Global Search"])
app.include_router(command_center.router,   prefix="/api/command-center",   tags=["Command Center"])
app.include_router(billing.router,          prefix="/api/billing",          tags=["Billing"])
app.include_router(competitor_import.router, prefix="/api/import",          tags=["Competitor Import"])
app.include_router(msp.router,              prefix="/api/msp",              tags=["MSP Console"])
app.include_router(chatops.router,          prefix="/api/chatops",          tags=["ChatOps"])
app.include_router(audit_log.router,        prefix="/api/audit-log",        tags=["Audit Activity Log"])
app.include_router(maturity.router,         prefix="/api/maturity",         tags=["Maturity Assessments"])
app.include_router(risk_treatment.router,   prefix="/api/risk/treatment",   tags=["Risk Treatment Plans"])
app.include_router(breach_simulation.router, prefix="/api/breach-simulation", tags=["Breach Cost Simulation"])
app.include_router(evidence_export.router,  prefix="/api/evidence-export",  tags=["Evidence Export"])
app.include_router(notifications.router,    prefix="/api/notifications",    tags=["Notifications"])


@app.get("/trust/{slug}")
async def serve_trust_center(slug: str) -> FileResponse:
    trust_path = Path(__file__).parent.parent.parent.parent / "frontend" / "public" / "trust.html"
    return FileResponse(trust_path)


@app.get("/")
@app.get("/login")
@app.get("/login/")
@app.get("/LOGIN")
@app.get("/LOGIN/")
@app.get("/dashboard")
@app.get("/dashboard/")
@app.get("/app")
@app.get("/app/")
@app.get("/demo")
@app.get("/pricing")
@app.get("/frameworks")
@app.get("/security")
@app.get("/monte-carlo")
@app.get("/mssp")
@app.head("/login")
@app.head("/login/")
@app.head("/LOGIN")
@app.head("/LOGIN/")
@app.head("/dashboard")
@app.head("/dashboard/")
async def serve_index() -> FileResponse:
    frontend_path = Path(__file__).parent.parent.parent.parent / "frontend" / "public" / "index.html"
    return FileResponse(frontend_path)




frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend" / "public"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/api/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "VALENCE GRC Dashboard", "version": "2.1.0"}


@app.get("/api/health/readiness", tags=["Health"])
async def health_readiness() -> dict[str, Any]:
    """Operator checklist — JWT, Postgres, Redis, CORS, SMTP, pen test attestation."""
    return collect_readiness()


@app.get("/api/status", tags=["Health"])
async def status(request: Request) -> dict[str, Any]:
    by_tenant = getattr(request.app.state, "latest_results_by_tenant", {})
    return {
        "status": "ok",
        "last_run_at": request.app.state.last_run_at,
        "last_run_id": request.app.state.last_run_id,
        "tenants_loaded": len(by_tenant),
        "connected_clients": len(request.app.state.websocket_clients),
    }


def run() -> None:
    """Entry point for `valence-api` script."""
    import uvicorn

    reload = os.getenv("VALENCE_RELOAD", "false").lower() in {"1", "true", "yes"}
    host = os.getenv("VALENCE_HOST", "0.0.0.0")
    port = int(os.getenv("VALENCE_PORT", "8000"))
    uvicorn.run(
        "grc_dashboard.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )
