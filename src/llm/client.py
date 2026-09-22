import os
import json
import time
import random
from pathlib import Path
from openai import OpenAI, APITimeoutError, RateLimitError, APIStatusError, APIConnectionError

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "enrich-v1.md"
PROMPT_VERSION = "enrich-v1"

# --- Stage 4: reliability settings ---
CLIENT_TIMEOUT_SECONDS = 30.0  # the SDK default is 10 minutes - far too long for an HTTP endpoint
MAX_RETRIES = 2                # our own retry count; the SDK's built-in retries are disabled below
BASE_BACKOFF_SECONDS = 1.0     # 1s, 2s, 4s... plus jitter


class ModelTimeoutError(Exception):
    """Raised when the model call times out, even after retries."""
    pass


def _get_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        timeout=CLIENT_TIMEOUT_SECONDS,
        max_retries=0,  # we handle retries ourselves - see _chat_completion_with_retry
    )


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with a little jitter: 1s, 2s, 4s (+ up to 0.5s random)."""
    return (BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))) + random.uniform(0, 0.5)


def _chat_completion_with_retry(messages: list[dict]):
    """Calls the model, retrying only on timeouts, 429, and 5xx.
    Never retries on 400, 401, or 403 - those will still be wrong on the
    next try, and on a metered free tier a pointless retry burns real quota.
    Returns (response, duration_ms)."""
    client = _get_client()
    attempt = 0

    while True:
        attempt += 1
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=os.environ["LLM_MODEL"],
                temperature=0.2,
                messages=messages,
            )
            duration_ms = (time.monotonic() - start) * 1000
            return response, duration_ms

        except APITimeoutError:
            if attempt > MAX_RETRIES:
                raise ModelTimeoutError(f"Model call timed out after {attempt} attempts")
            time.sleep(_backoff_seconds(attempt))

        except RateLimitError as e:
            if attempt > MAX_RETRIES:
                raise
            retry_after = getattr(e, "response", None)
            wait_seconds = _backoff_seconds(attempt)
            if retry_after is not None:
                header_value = retry_after.headers.get("Retry-After")
                if header_value:
                    try:
                        wait_seconds = float(header_value)
                    except ValueError:
                        pass  # not a plain number of seconds - fall back to our own backoff
            time.sleep(wait_seconds)

        except APIStatusError as e:
            if e.status_code >= 500 and attempt <= MAX_RETRIES:
                time.sleep(_backoff_seconds(attempt))
                continue
            raise  # 400/401/403 (and anything else) are never retried

        except APIConnectionError:
            if attempt > MAX_RETRIES:
                raise
            time.sleep(_backoff_seconds(attempt))


def call_model(book_payload: dict) -> str:
    """Send one book record to the model and return its raw text answer.
    No parsing or validation here - that's src/llm/parse.py.

    TEST HOOK: set LLM_FORCE_BROKEN=1 to skip the real call and return
    deliberately invalid output, to deterministically test the
    parse -> repair -> quarantine path without depending on whether the
    model chooses to obey a broken prompt."""
    if os.environ.get("LLM_FORCE_BROKEN") == "1":
        return '{"category": "not_a_real_category", "summary": "forced test failure", "quality_flags": [], "confidence": 5}'

    system_prompt = load_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(book_payload)},
    ]

    response, duration_ms = _chat_completion_with_retry(messages)

    from src.llm.cost_log import log_call
    usage = response.usage
    log_call(
        prompt_version=PROMPT_VERSION,
        model=os.environ["LLM_MODEL"],
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        duration_ms=duration_ms,
        repaired=False,
    )

    return response.choices[0].message.content


def call_model_repair(book_payload: dict, broken_output: str, error_message: str) -> str:
    """One repair attempt: send the model its own broken answer plus the exact
    validation error, and ask for a corrected version.

    TEST HOOK: set LLM_FORCE_BROKEN_TWICE=1 to also force the repair attempt
    to fail, proving the give-up-cleanly (422 + quarantine) path."""
    if os.environ.get("LLM_FORCE_BROKEN_TWICE") == "1":
        return '{"category": "still_not_real", "summary": "forced repair failure too", "quality_flags": [], "confidence": 5}'

    system_prompt = load_system_prompt()

    repair_instruction = (
        f"Your previous answer was rejected for this reason: {error_message}\n\n"
        f"Your previous answer was:\n{broken_output}\n\n"
        "Return only corrected JSON matching the schema. No explanation, no code fence."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(book_payload)},
        {"role": "assistant", "content": broken_output},
        {"role": "user", "content": repair_instruction},
    ]

    response, duration_ms = _chat_completion_with_retry(messages)

    from src.llm.cost_log import log_call
    usage = response.usage
    log_call(
        prompt_version=PROMPT_VERSION,
        model=os.environ["LLM_MODEL"],
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        duration_ms=duration_ms,
        repaired=True,
    )

    return response.choices[0].message.content