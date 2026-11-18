"""The one place that builds the `Tracer` the settings name. Never raises: a provider that cannot
be built (missing package, bad config) logs a warning and becomes `NullTracer`, so the app starts
and the turns run without traces (ATI, Vera)."""

import logging

from .models import Prices, TracingProvider
from .settings import ObservabilitySettings
from .tracer import NullTracer, Tracer

logger = logging.getLogger(__name__)


class TracingFactory:
    @staticmethod
    def create(settings: ObservabilitySettings, *, prices: Prices | None = None) -> Tracer:
        """Call it once at startup (FastAPI `lifespan`): `app.state.tracer = TracingFactory.create(settings)`.
        At shutdown: `await app.state.tracer.flush()`."""
        common = {"prices": prices, "flush_timeout": settings.tracing_flush_timeout_seconds}
        if settings.tracing_provider is TracingProvider.NONE:
            return NullTracer(**common)
        try:
            match settings.tracing_provider:
                case TracingProvider.LANGFUSE:
                    return TracingFactory._langfuse(settings, **common)
                case TracingProvider.OPIK:
                    return TracingFactory._opik(settings, **common)
                case TracingProvider.LANGSMITH:
                    return TracingFactory._langsmith(settings, **common)
        except Exception as exc:
            logger.warning("tracing provider %s unavailable (%s): running without traces", settings.tracing_provider, type(exc).__name__)
            return NullTracer(**common)
        raise ValueError(f"Unknown tracing provider: {settings.tracing_provider!r}")

    @staticmethod
    def _langfuse(settings: ObservabilitySettings, **common) -> Tracer:
        from langfuse import Langfuse

        from .langfuse_tracer import LangfuseTracer

        assert settings.langfuse_public_key and settings.langfuse_secret_key
        public_key = settings.langfuse_public_key.get_secret_value()
        client = Langfuse(
            public_key=public_key, secret_key=settings.langfuse_secret_key.get_secret_value(), host=settings.langfuse_host
        )
        return LangfuseTracer(client, public_key=public_key, **common)

    @staticmethod
    def _opik(settings: ObservabilitySettings, **common) -> Tracer:
        import opik

        from .opik_tracer import OpikTracer

        kwargs: dict = {"automatic_approvals": True, "install_mcp": False}
        if settings.opik_api_key:
            kwargs["api_key"] = settings.opik_api_key.get_secret_value()
            kwargs["workspace"] = settings.opik_workspace
        else:
            kwargs["use_local"] = True
        if settings.opik_url_override:
            kwargs["url_override"] = settings.opik_url_override
        opik.configure(**kwargs)
        return OpikTracer(project_name=settings.opik_project_name, **common)

    @staticmethod
    def _langsmith(settings: ObservabilitySettings, **common) -> Tracer:
        from langsmith import Client

        from .langsmith_tracer import LangSmithTracer

        assert settings.langsmith_api_key
        client = Client(api_key=settings.langsmith_api_key.get_secret_value(), api_url=settings.langsmith_endpoint)
        return LangSmithTracer(client, project_name=settings.langsmith_project, **common)
