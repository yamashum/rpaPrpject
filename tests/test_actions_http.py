import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow.actions_http import http_get, http_post


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"msg": "ok"}).encode())

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length) or b"{}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"echo": data}).encode())

    def log_message(self, format, *args):  # noqa: A003
        pass


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="t"), steps=[])
    return ExecutionContext(flow, {})


def run_server(server: HTTPServer):
    with server:
        server.serve_forever()


def test_http_get_post():
    server = HTTPServer(("localhost", 0), Handler)
    thread = threading.Thread(target=run_server, args=(server,), daemon=True)
    thread.start()
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    ctx = build_ctx()
    result_get = http_get(
        Step(id="g", action="http.get", params={"url": base_url}), ctx
    )
    assert result_get == {"msg": "ok"}

    result_post = http_post(
        Step(id="p", action="http.post", params={"url": base_url, "data": {"a": 1}}),
        ctx,
    )
    assert result_post == {"echo": {"a": 1}}

    server.shutdown()
    thread.join()
