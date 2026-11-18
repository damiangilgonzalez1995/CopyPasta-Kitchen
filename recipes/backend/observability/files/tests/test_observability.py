import logging
import time

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import SecretStr

from observability import (
    ModelPrice,
    NullTracer,
    ObservabilitySettings,
    Prices,
    RunInfo,
    TokenUsage,
    Tracer,
    TracingFactory,
    TracingProvider,
    UsageCollector,
    usage_from_messages,
)

RUN = RunInfo(thread_id="t1:conv-1", tenant_id="t1", user_id="u1", request_id="req-1", tags=["test"])
PRICES = Prices(by_model={"gpt-x": ModelPrice(input=2.0, output=8.0, cached_input=0.5)})


def ai(model: str, *, inp: int, out: int, cached: int = 0, text: str = "ok") -> AIMessage:
    return AIMessage(
        text,
        usage_metadata={"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out, "input_token_details": {"cache_read": cached}},
        response_metadata={"model_name": model},
    )


# --- usage and cost -------------------------------------------------------------------------


def test_usage_from_messages_reads_usage_metadata_and_cache():
    usages = usage_from_messages([HumanMessage("q"), ai("gpt-x", inp=100, out=20, cached=40), AIMessage("no usage")])
    assert usages == [TokenUsage(model="gpt-x", input_tokens=100, output_tokens=20, cached_input_tokens=40)]
    assert usages[0].total_tokens == 120


def test_prices_discount_cached_input_and_refuse_to_guess():
    usage = TokenUsage(model="gpt-x", input_tokens=100, output_tokens=20, cached_input_tokens=40)
    assert PRICES.cost_usd(usage) == pytest.approx((60 * 2.0 + 40 * 0.5 + 20 * 8.0) / 1e6)
    assert PRICES.cost_usd(TokenUsage(model="unknown-model", input_tokens=1)) is None
    assert Prices(by_model={"m": ModelPrice(input=1, output=1)}).cost_usd(TokenUsage(model="m", input_tokens=10, cached_input_tokens=10)) == pytest.approx(10 / 1e6)


async def test_usage_collector_sees_every_chat_model_call():
    collector = UsageCollector()
    model = GenericFakeChatModel(messages=iter([ai("gpt-x", inp=10, out=5), ai("gpt-x", inp=30, out=1, cached=30)]))
    await model.ainvoke("a", config={"callbacks": [collector]})
    await model.ainvoke("b", config={"callbacks": [collector]})
    assert [u.input_tokens for u in collector.usages] == [10, 30]
    assert (collector.input_tokens, collector.output_tokens, collector.cached_input_tokens) == (40, 6, 30)


# --- turn trace -----------------------------------------------------------------------------


async def test_null_tracer_still_gives_metadata_collector_and_summary(caplog):
    tracer = NullTracer(prices=PRICES)
    trace = tracer.begin(RUN)
    assert trace.config["metadata"] == {"thread_id": "t1:conv-1", "tenant_id": "t1", "user_id": "u1", "request_id": "req-1"}
    assert trace.config["tags"] == ["test"] and trace.config["run_name"] == "turn"
    assert trace.config["callbacks"] == [trace.usage]

    model = GenericFakeChatModel(messages=iter([ai("gpt-x", inp=100, out=20, cached=40)]))
    await model.ainvoke("q", config=trace.config)
    time.sleep(0.01)
    with caplog.at_level(logging.INFO, logger="observability.tracer"):
        summary = trace.finish()
    assert (summary.llm_calls, summary.input_tokens, summary.output_tokens, summary.cached_input_tokens) == (1, 100, 20, 40)
    assert summary.cost_usd == pytest.approx(0.00030) and summary.duration_ms >= 10 and summary.error is None
    assert "turn thread=t1:conv-1 tenant=t1 llm_calls=1 tokens=100/20 cached=40 cost_usd=0.000300" in caplog.text


def test_finish_records_the_error_class_only_and_unknown_cost():
    trace = NullTracer().begin(RUN)
    trace.usage.usages.append(TokenUsage(model="no-price", input_tokens=5))
    summary = trace.finish(error=RuntimeError("postgres://user:secret@host"))
    assert summary.error == "RuntimeError" and summary.cost_usd is None and "secret" not in summary.model_dump_json()


class Spy(BaseCallbackHandler):
    def __init__(self) -> None:
        self.starts: list[dict] = []

    def on_chat_model_start(self, serialized, messages, *, metadata=None, tags=None, **kwargs):
        self.starts.append({"metadata": dict(metadata or {}), "tags": list(tags or [])})


class SpyTracer(Tracer):
    def __init__(self) -> None:
        super().__init__()
        self.spy = Spy()
        self.flushed = 0

    def _callbacks(self, run):
        return [self.spy]

    def _metadata(self, run):
        return {"provider_session": run.thread_id}

    def _trace_id(self, run):
        return f"trace-{run.request_id}"

    def _flush(self):
        self.flushed += 1


async def test_provider_handler_receives_metadata_and_tags_of_the_run():
    tracer = SpyTracer()
    trace = tracer.begin(RUN)
    await GenericFakeChatModel(messages=iter([ai("gpt-x", inp=1, out=1)])).ainvoke("q", config=trace.config)
    assert tracer.spy.starts[0]["metadata"]["provider_session"] == "t1:conv-1"
    assert tracer.spy.starts[0]["metadata"]["request_id"] == "req-1" and "test" in tracer.spy.starts[0]["tags"]
    assert trace.finish().trace_id == "trace-req-1"
    await tracer.flush()
    assert tracer.flushed == 1


class BrokenTracer(Tracer):
    def _callbacks(self, run):
        raise ConnectionError("sk-secret inside the message")

    def _flush(self):
        raise ConnectionError("sk-secret inside the message")


class SlowTracer(NullTracer):
    def _flush(self):
        time.sleep(2)


async def test_tracing_failures_never_reach_the_turn(caplog):
    with caplog.at_level(logging.WARNING, logger="observability.tracer"):
        trace = BrokenTracer().begin(RUN)
        await BrokenTracer().flush()
        await SlowTracer(flush_timeout=0.05).flush()
    assert trace.config["callbacks"] == [trace.usage] and trace.config["metadata"]["thread_id"] == "t1:conv-1"
    assert "tracing disabled for this run (ConnectionError)" in caplog.text
    assert "tracing flush failed (ConnectionError)" in caplog.text and "flush timed out" in caplog.text
    assert "sk-secret" not in caplog.text


# --- settings and factory -------------------------------------------------------------------


def test_settings_default_to_no_tracing_and_check_each_provider(monkeypatch):
    assert ObservabilitySettings(_env_file=None).tracing_provider is TracingProvider.NONE
    with pytest.raises(ValueError, match="LANGFUSE_PUBLIC_KEY"):
        ObservabilitySettings(_env_file=None, tracing_provider="langfuse")
    with pytest.raises(ValueError, match="OPIK_URL_OVERRIDE"):
        ObservabilitySettings(_env_file=None, tracing_provider="opik")
    with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
        ObservabilitySettings(_env_file=None, tracing_provider="langsmith")
    monkeypatch.setenv("TRACING_TAGS", "prod, eu")
    monkeypatch.setenv("TRACING_PROVIDER", "opik")
    monkeypatch.setenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api")
    settings = ObservabilitySettings(_env_file=None)
    assert settings.tracing_tags == ["prod", "eu"] and settings.tracing_provider is TracingProvider.OPIK


def test_factory_none_and_fail_open(monkeypatch, caplog):
    assert isinstance(TracingFactory.create(ObservabilitySettings(_env_file=None)), NullTracer)
    settings = ObservabilitySettings(_env_file=None, tracing_provider="langsmith", langsmith_api_key=SecretStr("ls-x"))
    monkeypatch.setattr(TracingFactory, "_langsmith", staticmethod(lambda *a, **k: (_ for _ in ()).throw(ImportError("langsmith"))))
    with caplog.at_level(logging.WARNING):
        tracer = TracingFactory.create(settings)
    assert isinstance(tracer, NullTracer) and "langsmith unavailable (ImportError)" in caplog.text


def test_factory_builds_langsmith_offline():
    pytest.importorskip("langsmith")
    from observability.langsmith_tracer import LangSmithTracer

    settings = ObservabilitySettings(_env_file=None, tracing_provider="langsmith", langsmith_api_key=SecretStr("ls-x"), langsmith_project="p")
    tracer = TracingFactory.create(settings)
    assert isinstance(tracer, LangSmithTracer) and tracer.project_name == "p"
    callbacks = tracer.begin(RUN).config["callbacks"]
    assert type(callbacks[0]).__name__ == "LangChainTracer" and isinstance(callbacks[1], UsageCollector)


def test_factory_builds_langfuse_offline():
    pytest.importorskip("langfuse")
    from observability.langfuse_tracer import LangfuseTracer

    settings = ObservabilitySettings(
        _env_file=None,
        tracing_provider="langfuse",
        langfuse_public_key=SecretStr("pk-lf-test"),
        langfuse_secret_key=SecretStr("sk-lf-test"),
        langfuse_host="http://127.0.0.1:9",
    )
    tracer = TracingFactory.create(settings)
    assert isinstance(tracer, LangfuseTracer)
    config = tracer.begin(RUN).config
    assert isinstance(config["callbacks"][0], BaseCallbackHandler) and "langfuse" in type(config["callbacks"][0]).__module__
    assert config["metadata"]["langfuse_session_id"] == "t1:conv-1" and config["metadata"]["langfuse_user_id"] == "u1"


def test_factory_builds_opik_offline(monkeypatch):
    opik = pytest.importorskip("opik")
    from observability.opik_tracer import OpikTracer

    configured: list[dict] = []
    monkeypatch.setattr(opik, "configure", lambda **kwargs: configured.append(kwargs))
    monkeypatch.setenv("OPIK_URL_OVERRIDE", "http://127.0.0.1:9/api")
    settings = ObservabilitySettings(_env_file=None, tracing_provider="opik", opik_url_override="http://127.0.0.1:9/api", opik_project_name="p")
    tracer = TracingFactory.create(settings)
    assert isinstance(tracer, OpikTracer) and configured == [
        {"automatic_approvals": True, "install_mcp": False, "use_local": True, "url_override": "http://127.0.0.1:9/api"}
    ]
    callbacks = tracer.begin(RUN).config["callbacks"]
    assert type(callbacks[0]).__name__ == "OpikTracer" and tracer.project_name == "p"
