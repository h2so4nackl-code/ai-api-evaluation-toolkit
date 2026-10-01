# AI API Evaluation Toolkit

A small, local-first Python toolkit for checking OpenAI-compatible chat endpoints. It demonstrates endpoint health, HTTP and JSON validation, response-shape checks, latency measurement, timeout handling, retry behavior, and machine-readable evaluation reports.

This is a personal portfolio project. It does not represent employer or client work, and it contains no API keys, production credentials, or private evaluation data.

## What it demonstrates

- Positive, HTTP 4xx/5xx, malformed, empty, timeout, and transport-error cases
- A minimal schema check for `choices[0].message.content`
- Per-attempt status, error, and latency evidence
- Explicit `success`, `http_response_error`, `timeout`, `transport_failure`, `malformed_json`, and `invalid_schema` outcomes
- Configurable timeout, retry count, and latency budget
- JSON reports that are safe to attach to a bug or test run
- Automated tests using deterministic fakes instead of paid APIs

## Quick start

Create and activate the virtual environment before installing dependencies. On Windows PowerShell, use `.\.venv\Scripts\Activate.ps1` instead of `source .venv/bin/activate`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
```

Run the included local mock in one terminal:

```bash
python examples/mock_server.py
```

Then evaluate it in another:

```bash
ai-api-eval http://127.0.0.1:8080/v1/chat/completions
```

The command exits with code `0` only when all checks pass. A representative result is stored in [`reports/sample-report.json`](reports/sample-report.json).

## Checks

| Check | Evidence |
| --- | --- |
| Reachability | A response status was received |
| HTTP success | Final status is in the 2xx range |
| JSON validity | The body parses as UTF-8 JSON |
| Chat schema | A non-empty assistant content string exists |
| Latency | Final attempt stays inside the configured budget |
| Empty response | Parsed payload is not empty |

The top-level `failure_type` identifies the final failure category. HTTP error responses preserve their real status code; retryable `429` and `5xx` responses may be retried within the configured bound, while other `4xx` responses stop immediately.

## Project structure

```text
src/ai_api_evaluator/  evaluator and CLI
examples/              local mock endpoint
tests/                 deterministic unit tests
reports/               sanitized sample output
```

## Safety and limitations

- The tool deliberately does not accept an API key flag or persist headers.
- The sample uses loopback only; no external service is contacted.
- The schema check is intentionally small and educational, not a full OpenAPI validator.
- Response text is not copied into reports, reducing accidental data exposure.

## Suggested GitHub description

Local-first Python toolkit for OpenAI-compatible endpoint health, schema, latency, timeout, retry, and reporting checks.

## Suggested topics

`ai-evaluation`, `api-testing`, `quality-assurance`, `python`, `json`, `http`, `llm-testing`, `test-automation`

## License

MIT
