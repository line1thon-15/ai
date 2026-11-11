import json
import threading
import urllib.error
import urllib.request

import pytest

from app.providers import FakeProvider
from app.server import App, make_server

TOKEN = "test-token"


class Client:
    def __init__(self, base: str):
        self.base = base

    def request(self, method, path, body=None, token=TOKEN, raw=None):
        """(상태코드, JSON 본문) 반환. 4xx/5xx 도 예외 없이 돌려준다."""
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Internal-Token"] = token
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


@pytest.fixture
def start_server():
    """서버를 임의 포트로 띄운다. provider 를 바꿔 끼울 수 있다."""
    started = []

    def _start(provider=None):
        app = App(internal_token=TOKEN, provider=provider or FakeProvider(), provider_name="fake")
        httpd = make_server(app, port=0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return Client(f"http://127.0.0.1:{httpd.server_port}")

    yield _start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def client(start_server):
    return start_server()
