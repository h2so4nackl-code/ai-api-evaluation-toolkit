from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        json.loads(self.rfile.read(length) or b"{}")
        body = json.dumps(
            {"id": "demo-1", "choices": [{"message": {"role": "assistant", "content": "Mock response"}}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("Mock endpoint: http://127.0.0.1:8080/v1/chat/completions")
    ThreadingHTTPServer(("127.0.0.1", 8080), Handler).serve_forever()

