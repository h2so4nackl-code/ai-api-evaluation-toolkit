import io
import json
from urllib.error import URLError

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
    assert report["passed"] is False


def test_empty_content_fails_schema():
    payload = json.dumps({"choices": [{"message": {"content": ""}}]}).encode()
    report = evaluate_endpoint(EvaluationConfig("http://local.test", max_latency_ms=5_000), {}, lambda *_a, **_k: FakeResponse(payload))
    assert "non-empty string" in report["schema_errors"][0]


def test_retry_recovers_after_network_error():
    calls = iter([URLError("temporary"), FakeResponse(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())])
    def opener(*_args, **_kwargs):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item
    report = evaluate_endpoint(EvaluationConfig("http://local.test", retries=1, max_latency_ms=5_000), {}, opener)
    assert len(report["attempts"]) == 2
    assert report["passed"] is True

