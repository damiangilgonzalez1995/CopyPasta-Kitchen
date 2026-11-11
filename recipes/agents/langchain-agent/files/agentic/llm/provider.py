"""Factory: `LLMModel` + project settings -> LangChain chat model. The only place that knows provider classes."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from .models import LLMModel, LLMProviderName
from .settings import LLMSettings, get_llm_settings

_NOT_PASSED: Any = object()


class LLMProvider:
    @staticmethod
    def create_from_model(
        model: LLMModel,
        settings: LLMSettings | None = None,
        *,
        temperature: float | None = None,
        streaming: bool = False,
        reasoning_effort: str | None = _NOT_PASSED,
    ) -> BaseChatModel:
        """Build the chat model for `model`.

        - `temperature=None` -> not sent (reasoning models reject it).
        - `reasoning_effort` not passed -> the model's default (`LLMModel.reasoning_effort`).
        - Provider packages are imported lazily: install only the ones you use.
        - `settings=None` -> the project settings (`get_llm_settings()`); pass one only in tests.
        - Unknown provider -> ValueError. There is no silent default.
        """
        effort = model.reasoning_effort if reasoning_effort is _NOT_PASSED else reasoning_effort
        settings = settings or get_llm_settings()
        api_key = settings.api_key_for(model.provider.value)
        common: dict[str, Any] = {
            "timeout": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries,
            "streaming": streaming,
        }
        if temperature is not None:
            common["temperature"] = temperature

        match model.provider:
            case LLMProviderName.OPENAI:
                from langchain_openai import ChatOpenAI

                if effort is not None:
                    common["reasoning_effort"] = effort
                return ChatOpenAI(model=model.model_id, api_key=api_key, stream_usage=True, **common)

            case LLMProviderName.AZURE_OPENAI:
                from langchain_openai import AzureChatOpenAI

                if not settings.azure_openai_endpoint or not settings.azure_openai_api_version:
                    raise ValueError("Azure OpenAI needs azure_openai_endpoint and azure_openai_api_version")
                if effort is not None:
                    common["reasoning_effort"] = effort
                return AzureChatOpenAI(
                    azure_deployment=model.model_id,
                    azure_endpoint=settings.azure_openai_endpoint,
                    api_version=settings.azure_openai_api_version,
                    api_key=api_key,
                    stream_usage=True,
                    **common,
                )

            case LLMProviderName.ANTHROPIC:
                from langchain_anthropic import ChatAnthropic

                if effort is not None:
                    common["reasoning_effort"] = effort
                return ChatAnthropic(model=model.model_id, api_key=api_key, max_tokens=8192, **common)

            case LLMProviderName.GROQ:
                from langchain_groq import ChatGroq

                return ChatGroq(model=model.model_id, api_key=api_key, **common)

        raise ValueError(f"Unsupported provider: {model.provider!r}")
