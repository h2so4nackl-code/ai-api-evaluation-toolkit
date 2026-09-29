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
    schema_errors: list[str] = []

    def parse_payload(raw: bytes) -> tuple[Any, str | None]:
        try:
            return json.loads(raw.decode("utf-8")), None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, f"malformed JSON: {exc.__class__.__name__}"

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
            final_payload, parse_error = parse_payload(raw)
            schema_errors = (
                _validate_chat_schema(final_payload)
                if 200 <= status < 300 and final_payload is not None
                else []
            )
            if not 200 <= status < 300:
                outcome = "http_response_error"
                error = f"HTTP {status}"
            elif parse_error:
                outcome = "malformed_json"
                error = parse_error
            elif schema_errors:
                outcome = "invalid_schema"
                error = "invalid chat response schema"
            else:
                outcome = "success"
                error = None
            attempts.append(
                {
                    "attempt": attempt_number,
                    "http_status": status,
                    "latency_ms": latency_ms,
                    "outcome": outcome,
                    "error": error,
                }
            )
            if 200 <= status < 300:
                break
            if status != 429 and status < 500:
                break
        except urllib.error.HTTPError as exc:
            latency_ms = round((time.perf_counter() - started) * 1_000, 2)
            raw = exc.read()
            final_payload, parse_error = parse_payload(raw)
            schema_errors = []
            attempts.append(
                {
                    "attempt": attempt_number,
                    "http_status": exc.code,
                    "latency_ms": latency_ms,
                    "outcome": "http_response_error",
                    "error": f"HTTP {exc.code}"
                    + (f"; {parse_error}" if parse_error else ""),
                }
            )
            if exc.code != 429 and exc.code < 500:
                break
        except TimeoutError as exc:
            latency_ms = round((time.perf_counter() - started) * 1_000, 2)
            final_payload = None
            schema_errors = []
            attempts.append(
                {
                    "attempt": attempt_number,
                    "http_status": None,
                    "latency_ms": latency_ms,
                    "outcome": "timeout",
                    "error": exc.__class__.__name__,
                }
            )
        except urllib.error.URLError as exc:
            latency_ms = round((time.perf_counter() - started) * 1_000, 2)
            final_payload = None
            schema_errors = []
            is_timeout = isinstance(exc.reason, TimeoutError)
            attempts.append(
                {
                    "attempt": attempt_number,
                    "http_status": None,
                    "latency_ms": latency_ms,
                    "outcome": "timeout" if is_timeout else "transport_failure",
                    "error": "TimeoutError" if is_timeout else exc.__class__.__name__,
                }
            )

    last = attempts[-1]
    checks = {
        "reachable": last["http_status"] is not None,
        "http_ok": isinstance(last["http_status"], int) and 200 <= last["http_status"] < 300,
        "valid_json": final_payload is not None,
        "valid_chat_schema": final_payload is not None and not schema_errors,
        "within_latency_budget": last["latency_ms"] <= config.max_latency_ms,
        "non_empty_response": bool(final_payload),
    }
    passed = all(checks.values())
    failure_type = None if passed else last["outcome"]
    if failure_type == "success" and not checks["within_latency_budget"]:
        failure_type = "latency_budget_exceeded"
    return {
        "target": config.endpoint,
        "config": asdict(config),
        "attempts": attempts,
        "checks": checks,
        "schema_errors": schema_errors,
        "failure_type": failure_type,
        "passed": passed,
    }
