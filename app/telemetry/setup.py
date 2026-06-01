import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings


def setup_telemetry():
    if not settings.dt_endpoint_base or not settings.dt_api_token:
        logging.warning(
            "DT_ENDPOINT_BASE or DT_API_TOKEN is not set — "
            "OpenTelemetry data will NOT be exported to Dynatrace. "
            "Set both environment variables (or add them to a .env file) to enable export."
        )

    auth_header = {"Authorization": f"Api-Token {settings.dt_api_token}"}

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.deployment_environment,
            "telemetry.sdk.language": "python",
        }
    )

    # --- Tracer provider ---
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.traces_endpoint,
                headers=auth_header,
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)

    # --- Meter provider ---
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=settings.metrics_endpoint,
            headers=auth_header,
        ),
        export_interval_millis=15000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # --- Logger provider ---
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=settings.logs_endpoint,
                headers=auth_header,
            )
        )
    )
    set_logger_provider(logger_provider)

    # Bridge Python logging → OTel
    from opentelemetry.sdk._logs import LoggingHandler  # noqa: PLC0415
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)

    # --- Propagators ---
    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s [%(name)s] "
            "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s"
        ),
    )

    # --- Auto-instrumentation (applied after providers are set) ---
    from app.database import engine  # noqa: PLC0415 — import here to avoid circular
    SQLAlchemyInstrumentor().instrument(engine=engine)
    LoggingInstrumentor().instrument(set_logging_format=True)
    # FastAPIInstrumentor is applied after app creation via instrument_app()

    logging.getLogger(__name__).info(
        "OpenTelemetry configured — service=%s env=%s",
        settings.service_name,
        settings.deployment_environment,
    )
