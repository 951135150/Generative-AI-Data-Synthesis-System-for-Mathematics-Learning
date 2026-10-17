"""Optional OpenTelemetry tracing and metrics for the Calculus Atelier runtime."""

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from src.config import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservabilityStatus:
    enabled: bool
    exporter: str
    service_name: str
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "exporter": self.exporter,
            "service_name": self.service_name,
            "reason": self.reason,
        }


class ObservabilityRecorder:
    def __init__(self):
        self.request_duration = None
        self.request_counter = None
        self.generation_duration = None

    def configure(self, meter) -> None:
        self.request_duration = meter.create_histogram(
            "t2p.http.server.duration", unit="ms"
        )
        self.request_counter = meter.create_counter("t2p.http.server.requests")
        self.generation_duration = meter.create_histogram(
            "t2p.generation.duration", unit="ms"
        )

    def record_request(self, method: str, route: str, status_code: int, duration_ms: float):
        if self.request_counter is None or self.request_duration is None:
            return
        attributes = {
            "http.request.method": method,
            "http.route": route,
            "http.response.status_code": status_code,
        }
        self.request_counter.add(1, attributes)
        self.request_duration.record(duration_ms, attributes)

    def record_generation(self, pipeline: str, status: str, duration_ms: float):
        if self.generation_duration is not None:
            self.generation_duration.record(
                duration_ms, {"t2p.pipeline": pipeline, "t2p.status": status}
            )


recorder = ObservabilityRecorder()
_status = ObservabilityStatus(False, "none", Config.OTEL_SERVICE_NAME, "disabled")


def configure_observability(app, engine) -> ObservabilityStatus:
    global _status
    if not Config.OTEL_ENABLED:
        return _status
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        resource = Resource.create({"service.name": Config.OTEL_SERVICE_NAME})
        tracer_provider = TracerProvider(resource=resource)
        metric_readers = []
        exporter_name = "in-process"
        endpoint = Config.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")
        if endpoint:
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
            )
            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
                )
            )
            exporter_name = "otlp-http"
        elif Config.OTEL_CONSOLE_EXPORTER:
            tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            metric_readers.append(
                PeriodicExportingMetricReader(ConsoleMetricExporter())
            )
            exporter_name = "console"

        trace.set_tracer_provider(tracer_provider)
        meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
        metrics.set_meter_provider(meter_provider)
        recorder.configure(metrics.get_meter("t2p.runtime", "1.0"))

        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
        SQLAlchemyInstrumentor().instrument(
            engine=engine, tracer_provider=tracer_provider
        )
        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)
        _status = ObservabilityStatus(
            True, exporter_name, Config.OTEL_SERVICE_NAME, None
        )
    except Exception as exc:
        logger.exception("OpenTelemetry initialization failed")
        _status = ObservabilityStatus(
            False, "none", Config.OTEL_SERVICE_NAME, str(exc)
        )
    return _status


def current_trace_id() -> Optional[str]:
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        return format(context.trace_id, "032x") if context.is_valid else None
    except Exception:
        return None


def monotonic_ms() -> float:
    return time.perf_counter() * 1000
