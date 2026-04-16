import os
import logging
from abc import ABC, abstractmethod

from groq import APIError as GroqAPIError
from groq import AsyncGroq
from groq import RateLimitError as GroqRateLimitError


DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
logger = logging.getLogger(__name__)


def _configured_api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key in {"your_groq_api_key_here", "<SECRET>"}:
        return ""
    return api_key


def _configured_model() -> str:
    return os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL


class AIProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, require_json: bool = False) -> str:
        raise NotImplementedError


class GroqProvider(AIProvider):
    def __init__(self) -> None:
        api_key = _configured_api_key()
        self._client = AsyncGroq(api_key=api_key) if api_key else None
        if api_key:
            logger.info("Groq provider configured with model=%s key_prefix=%s", _configured_model(), f"{api_key[:6]}..." if len(api_key) >= 6 else "***")
        else:
            logger.warning("Groq provider is not configured. Set GROQ_API_KEY in backend/.env.")

    async def complete(self, prompt: str, require_json: bool = False) -> str:
        if not _configured_api_key() or self._client is None:
            raise RuntimeError("GROQ_API_KEY is not configured. Set a real key in backend/.env before generating reports.")

        kwargs = {}
        if require_json:
            kwargs["response_format"] = {"type": "json_object"}
            
        logger.info("Sending request to Groq model=%s prompt_chars=%s", _configured_model(), len(prompt))
        try:
            response = await self._client.chat.completions.create(
                model=_configured_model(),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise incident-response assistant. "
                            "Follow the user's prompt exactly and return only the requested content."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.1,
                max_completion_tokens=4096,
                **kwargs
            )
        except GroqRateLimitError as exc:
            raise RuntimeError(
                "Groq rate limit exceeded for the configured account or model. "
                "Try again shortly, switch to another Groq project, or choose a smaller model in GROQ_MODEL."
            ) from exc
        except GroqAPIError as exc:
            message = str(exc)
            if "invalid_api_key" in message.lower() or "invalid api key" in message.lower():
                raise RuntimeError(
                    "Groq rejected the API key. Check backend/.env and make sure GROQ_API_KEY contains the full real key, "
                    "then restart with docker compose down && docker compose up --build."
                ) from exc
            raise RuntimeError(f"Groq API error: {exc}") from exc

        content = response.choices[0].message.content if response.choices else ""
        logger.info("Received response from Groq model=%s completion_chars=%s", _configured_model(), len(content or ""))
        return (content or "").strip()


_provider: AIProvider = GroqProvider()


def get_provider() -> AIProvider:
    return _provider


def set_provider(provider: AIProvider) -> None:
    global _provider
    _provider = provider
