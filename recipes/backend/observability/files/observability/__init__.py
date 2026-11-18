"""Traces, tokens and cost of every agent turn, with the provider chosen in settings.

    tracer = TracingFactory.create(settings, prices=prices)      # startup, once
    trace = tracer.begin(RunInfo(thread_id=..., tenant_id=..., user_id=..., request_id=...))
    try:
        state = await ainvoke_graph(question, context=context, config=trace.config)
    finally:
        summary = trace.finish()                                 # tokens, cost, ms -> log + TurnSummary
    await tracer.flush()                                         # shutdown

The core (`agentic/`) never imports this package: it receives a `config` and that is all.
"""

from .factory import TracingFactory
from .models import ModelPrice, Prices, RunInfo, TokenUsage, TracingProvider, TurnSummary
from .settings import ObservabilitySettings
from .tracer import NullTracer, Tracer, TurnTrace
from .usage import UsageCollector, usage_from_messages

__all__ = [
    "ModelPrice",
    "NullTracer",
    "ObservabilitySettings",
    "Prices",
    "RunInfo",
    "TokenUsage",
    "Tracer",
    "TracingFactory",
    "TracingProvider",
    "TurnSummary",
    "TurnTrace",
    "UsageCollector",
    "usage_from_messages",
]
