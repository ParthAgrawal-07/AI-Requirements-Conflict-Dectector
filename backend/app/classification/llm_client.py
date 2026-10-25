"""The one place that talks to the LLM provider (Keval — US-05, US-60, NFR-38).

Everything that needs a model — the classifier, the brief drafter, later clarification questions
and suggestions — goes through :class:`LLMClient`, so timeouts, retries, the budget and output
validation are handled once:

* **Transport** (:class:`LLMTransport`) sends ``(system, user)`` and returns the reply text.
  :class:`AnthropicTransport` uses the official SDK; tests use :class:`FakeTransport`.
* **Timeout and transport retries** (429, 5xx, network) are the SDK's, configured from settings.
* **Budget**: every call first asks the :class:`~app.classification.budget.BudgetGuard`.
* **Validation**: :meth:`LLMClient.complete_json` parses the reply into a Pydantic model (the
  same model whose JSON Schema the prompt embeds). An invalid reply is re-asked once with the
  validation error; a second failure raises :class:`LLMOutputError` — nothing unvalidated is
  ever stored (FR-15).
* **Refusals** (``stop_reason == "refusal"`` after the server-side fallback) raise
  :class:`LLMRefusedError` and are not retried.

Requirement text reaches the model only inside the delimited data sections built by
``app.classification.prompting``; this module never builds prompts itself.
"""

import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.classification.budget import BudgetGuard, UnlimitedBudget
from app.core.config import Effort, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_OUTPUT_TOKENS = 2048  # classifier replies are a few hundred tokens; drafts a little more
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMError(Exception):
    """Base class: the AI layer failed, but the caller's session must carry on (FR-15)."""


class LLMUnavailableError(LLMError):
    """No usable provider (not configured, or it kept failing after the SDK's retries)."""


class LLMRefusedError(LLMError):
    """The model declined the request (after any server-side fallback)."""


class LLMOutputError(LLMError):
    """The reply did not validate against the expected schema, even after one re-ask."""


class LLMTransport(Protocol):
    def send(self, system: str, user: str) -> str:
        """Return the model's text reply. Raise :class:`LLMError` subclasses on failure."""
        ...


class AnthropicTransport:
    """Claude through the official ``anthropic`` SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        effort: Effort,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        import anthropic  # imported lazily: only workers that call the model need it

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout_seconds, max_retries=max_retries
        )
        self._model = model
        self._effort = effort

    def send(self, system: str, user: str) -> str:
        errors = self._anthropic
        try:
            response = self._client.beta.messages.create(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self._effort},
                # A safety decline is re-run server-side on Anthropic's recommended fallback.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except (errors.AuthenticationError, errors.PermissionDeniedError) as exc:
            raise LLMUnavailableError("The LLM provider rejected the credentials") from exc
        except errors.BadRequestError as exc:
            raise LLMError(f"The LLM request was invalid: {exc.message}") from exc
        except (errors.RateLimitError, errors.APIStatusError, errors.APIConnectionError) as exc:
            # The SDK already retried 429/5xx/network errors ``max_retries`` times.
            raise LLMUnavailableError("The LLM provider is unavailable") from exc

        if response.stop_reason == "refusal":
            raise LLMRefusedError("The model declined to answer")
        return "".join(block.text for block in response.content if block.type == "text")


@dataclass
class FakeTransport:
    """Scripted replies for tests: returns ``replies`` in order and records every prompt."""

    replies: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def send(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise LLMUnavailableError("FakeTransport has no more replies")
        return self.replies.pop(0)


class LLMClient:
    def __init__(self, transport: LLMTransport, budget: BudgetGuard | None = None) -> None:
        self._transport = transport
        self._budget = budget or UnlimitedBudget()

    def complete_text(self, system: str, user: str, *, project_id: uuid.UUID | None = None) -> str:
        """A plain-text reply (the brief drafter validates its own JSON)."""
        self._budget.reserve(project_id)
        return self._transport.send(system, user)

    def complete_json(
        self,
        system: str,
        user: str,
        output: type[T],
        *,
        project_id: uuid.UUID | None = None,
    ) -> T:
        """A reply validated into ``output``; re-asks once with the validation error."""
        reply = self.complete_text(system, user, project_id=project_id)
        try:
            return _parse(reply, output)
        except (ValueError, ValidationError) as first:
            logger.info("LLM reply did not validate (%s); asking again", type(first).__name__)
            retry_user = (
                f"{user}\n\nYour previous reply was not valid: {_short(first)}\n"
                "Reply again with only the JSON object that matches the schema."
            )
            reply = self.complete_text(system, retry_user, project_id=project_id)
            try:
                return _parse(reply, output)
            except (ValueError, ValidationError) as second:
                raise LLMOutputError(f"Invalid model output: {_short(second)}") from second

    def as_draft_llm(self) -> Callable[[str, str], str]:
        """The ``(system, user) -> text`` callable ``app.context.drafter.BriefDrafter`` takes."""
        return lambda system, user: self.complete_text(system, user)


def _parse(reply: str, output: type[T]) -> T:
    text = _FENCE.sub("", reply.strip()).strip()
    data: Any = json.loads(text)
    return output.model_validate(data)


def _short(error: Exception) -> str:
    return str(error).splitlines()[0][:300] if str(error) else type(error).__name__


@lru_cache
def get_llm_client() -> LLMClient | None:
    """The configured client, or ``None`` when no API key is set (rules-only mode)."""
    settings = get_settings()
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    if not key:
        return None
    if settings.llm_provider != "anthropic":
        raise LLMUnavailableError(f"LLM provider {settings.llm_provider!r} is not implemented")
    from app.classification.budget import get_budget_guard

    transport = AnthropicTransport(
        api_key=key,
        model=settings.llm_model,
        effort=settings.llm_effort,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    return LLMClient(transport, get_budget_guard())
