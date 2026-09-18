import os
import json
from pathlib import Path
from openai import OpenAI

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "enrich-v1.md"
PROMPT_VERSION = "enrich-v1"


def _get_client() -> OpenAI:
    return OpenAI(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
    )


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def call_model(book_payload: dict) -> str:
    """Send one book record to the model and return its raw text answer.
    No parsing or validation here - Stage 3 handles that.

    TEST HOOK: set LLM_FORCE_BROKEN=1 to skip the real call and return
    deliberately invalid output, to deterministically test the
    parse -> repair -> quarantine path without depending on whether the
    model chooses to obey a broken prompt."""
    if os.environ.get("LLM_FORCE_BROKEN") == "1":
        return '{"category": "not_a_real_category", "summary": "forced test failure", "quality_flags": [], "confidence": 5}'

    client = _get_client()
    system_prompt = load_system_prompt()

    response = client.chat.completions.create(
        model=os.environ["LLM_MODEL"],
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(book_payload)},
        ],
    )

    return response.choices[0].message.content


def call_model_repair(book_payload: dict, broken_output: str, error_message: str) -> str:
    """One repair attempt: send the model its own broken answer plus the exact
    validation error, and ask for a corrected version.

    TEST HOOK: set LLM_FORCE_BROKEN_TWICE=1 to also force the repair attempt
    to fail, proving the give-up-cleanly (422 + quarantine) path."""
    if os.environ.get("LLM_FORCE_BROKEN_TWICE") == "1":
        return '{"category": "still_not_real", "summary": "forced repair failure too", "quality_flags": [], "confidence": 5}'

    client = _get_client()
    system_prompt = load_system_prompt()

    repair_instruction = (
        f"Your previous answer was rejected for this reason: {error_message}\n\n"
        f"Your previous answer was:\n{broken_output}\n\n"
        "Return only corrected JSON matching the schema. No explanation, no code fence."
    )

    response = client.chat.completions.create(
        model=os.environ["LLM_MODEL"],
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(book_payload)},
            {"role": "assistant", "content": broken_output},
            {"role": "user", "content": repair_instruction},
        ],
    )

    return response.choices[0].message.content