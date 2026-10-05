import logging

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


def configure_telemetry(span_processor=None, metric_reader=None, log_processor=None):
    """Send traces, metrics, and logs to stdout until a collector is available.

    The metric export interval follows OTEL_METRIC_EXPORT_INTERVAL (default 60s).
    Only the first call takes effect, so tests can install in-memory exporters
    before the app module configures the console ones.
    """
    global _configured
    if _configured:
        return
    _configured = True
    resource = Resource.create({"service.name": SERVICE_NAME})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor or BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    reader = metric_reader or PeriodicExportingMetricReader(ConsoleMetricExporter())
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(log_processor or BatchLogRecordProcessor(ConsoleLogExporter()))
    set_logger_provider(logger_provider)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(LoggingHandler(logger_provider=logger_provider))
