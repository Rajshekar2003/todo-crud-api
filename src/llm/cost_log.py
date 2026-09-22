import json
import sys
from datetime import datetime, timezone


def log_call(prompt_version: str, model: str, input_tokens: int, output_tokens: int,
             duration_ms: float, repaired: bool) -> None:
    """One structured log line per model call, written to stdout.
    Following Twelve-Factor logging: write to stdout, let the environment
    route it, rather than inventing a log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "llm_call",
        "prompt_version": prompt_version,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": round(duration_ms, 1),
        "repaired": repaired,
    }
    print(json.dumps(entry), file=sys.stdout)