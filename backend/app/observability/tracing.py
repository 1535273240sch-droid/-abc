"""OpenTelemetry tracing setup.

Provides distributed tracing for the FastAPI application, including
automatic instrumentation of HTTP requests, database queries, and Redis
operations.

Usage (in main.py at startup):

    from app.observability.tracing import setup_tracing
    setup_tracing()
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_tracer_provider = None


def setup_tracing() -> None:
    """Initialise OpenTelemetry tracing if enabled."""
    if not settings.otel_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSortExporter

        resource = Resource.create({
            "service.name": settings.otel_service_name,
            "service.version": settings.app_version,
            "deployment.environment": settings.environment,
        })

        provider = TracerProvider(resource=resource)
        exporter = OTLPSortExporter(
            endpoint=settings.otel_endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        global _tracer_provider
        _tracer_provider = provider

        logger.info("OpenTelemetry tracing initialised (endpoint=%s)", settings.otel_endpoint)

    except ImportError:
        logger.warning("opentelemetry packages not installed; tracing disabled")
    except Exception as exc:  # noqa: BLE001
        logger.warning("tracing setup failed: %s", exc)


def shutdown_tracing() -> None:
    """Flush and shutdown the tracer provider."""
    global _tracer_provider
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
        except Exception:  # noqa: BLE001
            pass
        _tracer_provider = None


def get_tracer(name: str = __name__):
    """Return a tracer instance (or a no-op if tracing is disabled)."""
    if not settings.otel_enabled:
        return _NoopTracer()
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except Exception:  # noqa: BLE001
        return _NoopTracer()


class _NoopSpan:
    """No-op span when tracing is disabled."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value):
        pass

    def set_status(self, status):
        pass

    def record_exception(self, exc):
        pass

    def add_event(self, name: str, attributes=None):
        pass


class _NoopTracer:
    """No-op tracer when tracing is disabled."""

    def start_as_current_span(self, name: str, **kwargs):
        return _NoopSpan()

    def start_span(self, name: str, **kwargs):
        return _NoopSpan()
