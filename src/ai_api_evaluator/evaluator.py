from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class EvaluationConfig:
    endpoint: str
    timeout_seconds: float = 2.0
    retries: int = 1
    max_latency_ms: float = 1_000.0


def _validate_chat_schema(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["response must be a JSON object"]
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ["choices must be a non-empty array"]
    first = choices[0]
    if not isinstance(first, dict):
        return ["choices[0] must be an object"]
    message = first.get("message")
    if not isinstance(message, dict):
        errors.append("choices[0].message must be an object")
    elif not isinstance(message.get("content"), str) or not message["content"].strip():
        errors.append("choices[0].message.content must be a non-empty string")
    return errors


def evaluate_endpoint(
    config: EvaluationConfig,
    request_body: dict[str, Any],
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Evaluate one endpoint without storing credentials or response content."""
    attempts: list[dict[str, Any]] = []
    final_payload: Any = None

    for attempt_number in range(1, config.retries + 2):
        request = urllib.request.Request(
            config.endpoint,
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with opener(request, timeout=config.timeout_seconds) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
            latency_ms = round((time.perf_counter() - started) * 1_000, 2)
            try:
                final_payload = json.loads(raw.decode("utf-8"))
                parse_error = None
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                final_payload = None
                parse_error = f"malformed JSON: {exc.__class__.__name__}"
            attempts.append(
                {
                    "attempt": attempt_number,
                    "http_status": status,
                    "latency_ms": latency_ms,
                    "error": parse_error,
                }
            )
            if 200 <= status < 300:
                break
        except (TimeoutError, urllib.error.URLError) as exc:
            latency_ms = round((time.perf_counter() - started) * 1_000, 2)
            attempts.append(
                {
                    "attempt": attempt_number,
                    "http_status": None,
                    "latency_ms": latency_ms,
                    "error": exc.__class__.__name__,
                }
            )

    last = attempts[-1]
    schema_errors = _validate_chat_schema(final_payload) if final_payload is not None else []
    checks = {
        "reachable": last["http_status"] is not None,
        "http_ok": isinstance(last["http_status"], int) and 200 <= last["http_status"] < 300,
        "valid_json": final_payload is not None,
        "valid_chat_schema": final_payload is not None and not schema_errors,
        "within_latency_budget": last["latency_ms"] <= config.max_latency_ms,
        "non_empty_response": bool(final_payload),
    }
    return {
        "target": config.endpoint,
        "config": asdict(config),
        "attempts": attempts,
        "checks": checks,
        "schema_errors": schema_errors,
        "passed": all(checks.values()),
    }

