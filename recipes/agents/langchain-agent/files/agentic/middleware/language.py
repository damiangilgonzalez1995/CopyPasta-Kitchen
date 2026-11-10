"""Example middleware: remind the model of the answer language on every model call.

Pattern: a `build_*_middleware(...)` factory returns a `@wrap_model_call` function that changes
the request only for that call with `request.override(...)`. The stored history is untouched.
"""

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain_core.messages import SystemMessage

LANGUAGE_NAMES = {"es": "Spanish", "en": "English", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese"}


def build_language_middleware():
    @wrap_model_call
    async def language_reminder(
        request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        context = request.runtime.context if request.runtime else None
        language = getattr(context, "language", None)
        if not language:
            return await handler(request)
        name = LANGUAGE_NAMES.get(language, language)
        reminder = SystemMessage(f"Answer in {name}, whatever the language of the documents.")
        return await handler(request.override(messages=[*request.messages, reminder]))

    return language_reminder
