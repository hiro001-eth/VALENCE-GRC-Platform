"""OpenTelemetry observability and APM middleware/instrumentation setup."""
from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Check if OpenTelemetry is installed
HAS_OPENTELEMETRY = False
try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    HAS_OPENTELEMETRY = True
except ImportError:
    pass


def setup_observability(app: Any) -> None:
    """Auto-instrument FastAPI application and database queries with OpenTelemetry."""
    if not HAS_OPENTELEMETRY:
        logger.info(
            "observability_disabled",
            reason="OpenTelemetry packages not installed. Run: pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy",
        )
        return

    # Check environment configuration
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not otlp_endpoint and os.getenv("VALENCE_ENV", "development").lower() == "production":
        logger.warning(
            "otel_endpoint_missing",
            message="Production mode should define OTEL_EXPORTER_OTLP_ENDPOINT for APM tracking",
        )

    try:
        # Step 1: Initialize Tracer Provider
        resource = Resource.create(attributes={
            "service.name": "valence-grc-api",
            "service.namespace": "valence",
            "deployment.environment": os.getenv("VALENCE_ENV", "development"),
        })
        provider = TracerProvider(resource=resource)
        
        # Step 2: Configure Span Processor (OTLP/gRPC Exporter)
        if otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            span_processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(span_processor)
            logger.info("otel_exporter_connected", endpoint=otlp_endpoint)
        else:
            # Fallback to console span exporter in development
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            logger.info("otel_console_exporter_active")

        trace.set_tracer_provider(provider)

        # Step 3: Auto-instrument FastAPI
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("otel_fastapi_instrumented")

        # Step 4: Auto-instrument SQLAlchemy
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

            from grc_dashboard.db.session import engine
            SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
            logger.info("otel_sqlalchemy_instrumented")
        except Exception as db_exc:
            logger.warning("otel_sqlalchemy_instrumentation_skipped", error=str(db_exc))

    except Exception as exc:
        logger.error("observability_setup_failed", error=str(exc))
