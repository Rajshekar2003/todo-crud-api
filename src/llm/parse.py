import json
import re
from pydantic import ValidationError
from src.llm.schema import EnrichmentOutput


def extract_json_object(raw_text: str) -> dict:
    """Models sometimes wrap JSON in a code fence, or add text before/after it.
    Strip that and parse the JSON object. Raises ValueError if none can be found."""
    text = raw_text.strip()

    # Strip a ```json ... ``` or ``` ... ``` fence if present
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Fall back to grabbing the first { ... last } if there's still stray text around it
    if not text.startswith("{"):
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    return json.loads(text)  # raises json.JSONDecodeError if still invalid


def parse_and_validate(raw_text: str) -> tuple[EnrichmentOutput | None, str | None]:
    """Try to turn a model's raw text answer into a validated EnrichmentOutput.
    Returns (result, None) on success, or (None, error_message) on failure.
    Never raises - always one of the two."""
    try:
        obj = extract_json_object(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        return None, f"Could not parse JSON from model output: {e}"

    try:
        result = EnrichmentOutput(**obj)
    except ValidationError as e:
        return None, f"Output failed schema validation: {e}"

    return result, None