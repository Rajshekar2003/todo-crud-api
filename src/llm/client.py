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
    No parsing or validation here - Stage 3 handles that."""
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