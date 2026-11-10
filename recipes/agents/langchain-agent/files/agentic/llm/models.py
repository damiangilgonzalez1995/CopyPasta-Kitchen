"""Catalogue of the models the app may use. Add a member to use a new model; nothing else changes."""

from enum import Enum


class LLMProviderName(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    GROQ = "groq"


class LLMModel(Enum):
    """`(provider, model_id, reasoning_effort)`.

    - `model_id` is what the provider expects. For Azure OpenAI it is the *deployment name*.
    - `reasoning_effort` is the default for that model (`None` = do not send it). Only send it
      to models that accept it.
    """

    # OpenAI
    GPT_4_1 = (LLMProviderName.OPENAI, "gpt-4.1", None)
    GPT_4_1_MINI = (LLMProviderName.OPENAI, "gpt-4.1-mini", None)
    GPT_4_1_NANO = (LLMProviderName.OPENAI, "gpt-4.1-nano", None)
    # Anthropic
    CLAUDE_SONNET_5_5 = (LLMProviderName.ANTHROPIC, "claude-sonnet-5-5", None)
    CLAUDE_HAIKU_5_5 = (LLMProviderName.ANTHROPIC, "claude-haiku-5-5", None)
    # Azure OpenAI: model_id = your deployment name
    AZURE_GPT_4_1 = (LLMProviderName.AZURE_OPENAI, "gpt-4.1", None)
    # Groq
    LLAMA_3_3_70B = (LLMProviderName.GROQ, "llama-3.3-70b-versatile", None)

    def __init__(self, provider: LLMProviderName, model_id: str, reasoning_effort: str | None) -> None:
        self.provider = provider
        self.model_id = model_id
        self.reasoning_effort = reasoning_effort

    @classmethod
    def from_id(cls, model_id: str) -> "LLMModel":
        """Member for a model id read from settings/env. Unknown id -> ValueError listing the valid ones."""
        for member in cls:
            if member.model_id == model_id:
                return member
        valid = ", ".join(sorted({m.model_id for m in cls}))
        raise ValueError(f"Unknown model id {model_id!r}. Valid: {valid}")
