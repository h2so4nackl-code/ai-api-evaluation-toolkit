import io
import json
from urllib.error import HTTPError, URLError

import pytest

from ai_api_evaluator.evaluator import EvaluationConfig, evaluate_endpoint


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._stream = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._stream.read()


def test_valid_response_passes():
    payload = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
    report = evaluate_endpoint(EvaluationConfig("http://local.test", max_latency_ms=5_000), {}, lambda *_a, **_k: FakeResponse(payload))
    assert report["passed"] is True


def test_malformed_json_is_reported():
    report = evaluate_endpoint(EvaluationConfig("http://local.test", max_latency_ms=5_000), {}, lambda *_a, **_k: FakeResponse(b"not-json"))
    assert report["checks"]["valid_json"] is False
    assert report["failure_type"] == "malformed_json"
    assert report["passed"] is False


def test_empty_content_fails_schema():
    payload = json.dumps({"choices": [{"message": {"content": ""}}]}).encode()
    report = evaluate_endpoint(EvaluationConfig("http://local.test", max_latency_ms=5_000), {}, lambda *_a, **_k: FakeResponse(payload))
    assert "non-empty string" in report["schema_errors"][0]
    assert report["failure_type"] == "invalid_schema"


def test_retry_recovers_after_network_error():
    calls = iter([URLError("temporary"), FakeResponse(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())])
    def opener(*_args, **_kwargs):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item
    report = evaluate_endpoint(EvaluationConfig("http://local.test", retries=1, max_latency_ms=5_000), {}, opener)
    assert len(report["attempts"]) == 2
    assert report["attempts"][0]["outcome"] == "transport_failure"
    assert report["passed"] is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_http_error_preserves_status_and_category(status):
    body = json.dumps({"error": {"message": "synthetic failure"}}).encode()

    def opener(request, **_kwargs):
        raise HTTPError(request.full_url, status, "synthetic", None, io.BytesIO(body))

    report = evaluate_endpoint(
        EvaluationConfig("http://local.test", retries=0, max_latency_ms=5_000),
        {},
        opener,
    )

    assert report["attempts"] == [
        {
            "attempt": 1,
            "http_status": status,
            "latency_ms": report["attempts"][0]["latency_ms"],
            "outcome": "http_response_error",
            "error": f"HTTP {status}",
        }
    ]
    assert report["checks"]["reachable"] is True
    assert report["checks"]["http_ok"] is False
    assert report["failure_type"] == "http_response_error"
    assert report["passed"] is False


def test_timeout_is_distinct_from_transport_failure():
    def opener(*_args, **_kwargs):
        raise TimeoutError("synthetic timeout")

    report = evaluate_endpoint(
        EvaluationConfig("http://local.test", retries=0), {}, opener
    )

    assert report["attempts"][0]["outcome"] == "timeout"
    assert report["failure_type"] == "timeout"
    assert report["checks"]["reachable"] is False


def test_connection_failure_is_distinct_from_timeout():
    def opener(*_args, **_kwargs):
        raise URLError("connection refused")

    report = evaluate_endpoint(
        EvaluationConfig("http://local.test", retries=0), {}, opener
    )

    assert report["attempts"][0]["outcome"] == "transport_failure"
    assert report["failure_type"] == "transport_failure"
    assert report["checks"]["reachable"] is False


def test_retryable_http_error_can_recover():
    body = json.dumps({"error": {"message": "try later"}}).encode()
    success = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
    calls = 0

    def opener(request, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(request.full_url, 503, "synthetic", None, io.BytesIO(body))
        return FakeResponse(success)

    report = evaluate_endpoint(
        EvaluationConfig("http://local.test", retries=1, max_latency_ms=5_000),
        {},
        opener,
    )

    assert [attempt["outcome"] for attempt in report["attempts"]] == [
        "http_response_error",
        "success",
    ]
    assert report["passed"] is True
