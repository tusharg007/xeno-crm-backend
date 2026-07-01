"""Shared Groq helpers for bounded, retryable LLM calls."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from langchain_groq import ChatGroq

from config import settings


logger = logging.getLogger(__name__)

T = TypeVar("T")

GROQ_TIMEOUT_SECONDS = 12.0
GROQ_RETRY_ATTEMPTS = 3
GROQ_BACKOFF_SECONDS = 0.75

GROQ_UNAVAILABLE_MESSAGE = (
    "I could not reach Groq after a few retries. The local analytics and campaign "
    "tools are still available, so try a saved demo prompt or retry in a minute."
)


def build_groq_model(temperature: float) -> ChatGroq:
    """Create a ChatGroq model from app settings.

    Settings are instantiated once in config.py, so the API key is read from the
    environment once at process startup instead of per request.
    """
    return ChatGroq(
        model=settings.LLM_MODEL,
        temperature=temperature,
        groq_api_key=settings.GROQ_API_KEY,
        timeout=GROQ_TIMEOUT_SECONDS,
        max_retries=0,
    )


async def retry_async_groq_call(
    operation: Callable[[], Awaitable[T]],
    *,
    label: str,
) -> T:
    """Run an async Groq operation with timeout and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(GROQ_RETRY_ATTEMPTS):
        try:
            return await asyncio.wait_for(operation(), timeout=GROQ_TIMEOUT_SECONDS + 2)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "%s failed on attempt %s/%s: %s",
                label,
                attempt + 1,
                GROQ_RETRY_ATTEMPTS,
                exc,
            )
            if attempt < GROQ_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(GROQ_BACKOFF_SECONDS * (2**attempt))
    raise RuntimeError(f"{label} failed after retries") from last_error


def retry_sync_groq_call(
    operation: Callable[[], T],
    *,
    label: str,
) -> T:
    """Run a sync Groq operation with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(GROQ_RETRY_ATTEMPTS):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            logger.warning(
                "%s failed on attempt %s/%s: %s",
                label,
                attempt + 1,
                GROQ_RETRY_ATTEMPTS,
                exc,
            )
            if attempt < GROQ_RETRY_ATTEMPTS - 1:
                time.sleep(GROQ_BACKOFF_SECONDS * (2**attempt))
    raise RuntimeError(f"{label} failed after retries") from last_error
