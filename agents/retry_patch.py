"""
Monkey-patches ADK's Gemini LLM to retry on 503/429 with exponential back-off.
Import this module once before any Agent is used.
"""
from __future__ import annotations
import asyncio
import inspect
import logging
import random

logger = logging.getLogger(__name__)

MAX_RETRIES = 8


def apply():
    try:
        import google.adk.models.google_llm as _m

        # Find the LLM class — try known names first, then scan
        llm_cls = None
        for name in ("Gemini", "GoogleLLM", "GeminiLLM"):
            llm_cls = getattr(_m, name, None)
            if llm_cls and hasattr(llm_cls, "generate_content_async"):
                break
            llm_cls = None

        if llm_cls is None:
            for name, obj in inspect.getmembers(_m, inspect.isclass):
                if hasattr(obj, "generate_content_async"):
                    llm_cls = obj
                    break

        if llm_cls is None:
            logger.error("retry_patch: could not find LLM class — patch NOT applied")
            return

        original = llm_cls.generate_content_async

        async def _with_retry(self, llm_request, stream=False):
            for attempt in range(MAX_RETRIES):
                try:
                    async for chunk in original(self, llm_request, stream=stream):
                        yield chunk
                    return
                except Exception as e:
                    msg = str(e)
                    retryable = any(k in msg for k in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
                    if retryable and attempt < MAX_RETRIES - 1:
                        # 5s, 10s, 20s, 40s, 80s, 120s, 120s …
                        delay = min(120.0, 5 * (2 ** attempt) + random.uniform(0, 2))
                        logger.warning(
                            "⏳ LLM transient error (attempt %d/%d), retrying in %.0fs | %s",
                            attempt + 1, MAX_RETRIES, delay, msg[:80],
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

        llm_cls.generate_content_async = _with_retry
        logger.info("✅ retry_patch applied to %s (up to %d retries, max 120s delay)", llm_cls.__name__, MAX_RETRIES)

    except Exception as e:
        logger.error("❌ retry_patch failed to apply: %s", e, exc_info=True)


apply()
