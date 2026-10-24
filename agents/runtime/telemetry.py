"""OpenTelemetry: one tracer provider, OTLP/HTTP to the collector when configured.

Pydantic AI instruments every model request and tool call as spans once
Agent.instrument_all is given the provider; GuardedToolset adds its own
span per tool call with the policy decision.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = logging.getLogger("agent.telemetry")


def setup_tracing(service_name: str = "agent-runtime") -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
        )
        log.info("tracing to %s", endpoint)
    else:
        log.info("OTEL_EXPORTER_OTLP_ENDPOINT not set; traces stay in-process")
    trace.set_tracer_provider(provider)

    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.instrumented import InstrumentationSettings

        Agent.instrument_all(InstrumentationSettings(tracer_provider=provider))
    except Exception as e:  # instrumentation is best effort
        log.warning("pydantic-ai instrumentation not enabled: %s", e)
    return provider
