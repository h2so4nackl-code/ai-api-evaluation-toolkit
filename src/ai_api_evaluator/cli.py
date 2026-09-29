from __future__ import annotations

import argparse
import json

from .evaluator import EvaluationConfig, evaluate_endpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an OpenAI-compatible chat endpoint")
    parser.add_argument("endpoint", help="Use a local mock or an endpoint that needs no secret")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    request_body = {"model": "demo-model", "messages": [{"role": "user", "content": "health check"}]}
    report = evaluate_endpoint(
        EvaluationConfig(args.endpoint, timeout_seconds=args.timeout, retries=args.retries),
        request_body,
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

