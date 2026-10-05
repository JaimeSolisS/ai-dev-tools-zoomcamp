import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


SERVICE_NAME = "order-tracker"


_configured = False


def default_exporters():
    """Use OTLP when OTEL_EXPORTER_OTLP_ENDPOINT is set (the Collector in Compose), else stdout."""
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(), OTLPMetricExporter(), OTLPLogExporter()
    return ConsoleSpanExporter(), ConsoleMetricExporter(), ConsoleLogExporter()


def configure_telemetry(span_processor=None, metric_reader=None, log_processor=None):
    """Send traces, metrics, and logs to the OTLP endpoint, or to stdout without one.

    The metric export interval follows OTEL_METRIC_EXPORT_INTERVAL (default 60s).
    Only the first call takes effect, so tests can install in-memory exporters
    before the app module configures the default ones.
    """
    global _configured
    if _configured:
        return
    _configured = True
    resource = Resource.create({"service.name": SERVICE_NAME})
    span_exporter, metric_exporter, log_exporter = default_exporters()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor or BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    reader = metric_reader or PeriodicExportingMetricReader(metric_exporter)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(log_processor or BatchLogRecordProcessor(log_exporter))
    set_logger_provider(logger_provider)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(LoggingHandler(logger_provider=logger_provider))
