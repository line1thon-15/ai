"""AI 서버: 상태 없는 내부 HTTP 서비스 (AI-1).

- 백엔드(8080)가 내부 API로 호출하고, 이 서버는 8081에서 받는다.
- /health 만 인증 없이 열려 있고, 나머지는 X-Internal-Token 이 맞아야 한다.
- 운영 로그에는 "메서드 경로 -> 상태코드"만 남긴다. 프롬프트·출력·요청 본문은 남기지 않는다 (AI-2).
- 표준 라이브러리만 사용한다. 새 엔드포인트는 ROUTES 에 한 줄 추가하면 된다.
"""
import hmac
import json
import logging
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pydantic import ValidationError

from .judge import Judge
from .practice import PracticeEngine
from .providers import LLMProvider
from .scenarios import InvalidVariant, UnknownScenario
from .schemas import (FeedbackRequest, JudgeRequest, StartRequest, SummaryRequest, SummaryResponse,
                      TurnRequest, VariantRequest)
from .summary import generate_summary
from .variation import InvalidAxis, Variator

log = logging.getLogger("ai.server")

MAX_BODY_BYTES = 64 * 1024
TOKEN_HEADER = "X-Internal-Token"


@dataclass
class App:
    internal_token: str
    provider: LLMProvider
    provider_name: str = "fake"
    engine: PracticeEngine | None = None
    variator: Variator | None = None
    judge: Judge | None = None

    def __post_init__(self):
        if self.engine is None:
            self.engine = PracticeEngine(self.provider)
        if self.variator is None:
            self.variator = Variator(self.provider, self.engine.scenarios)
        if self.judge is None:
            self.judge = Judge(self.provider, self.engine.scenarios)


class _HttpError(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code


# ---- 엔드포인트 -------------------------------------------------------------

def _health(app: App, body):
    return 200, {"status": "ok", "provider": app.provider_name}


def _summary(app: App, body):
    """T-75 보호자 학습 요약. AI 실패 시 summary=null (백엔드는 요약 칸만 비움)."""
    try:
        req = SummaryRequest.model_validate(body)
    except ValidationError as e:
        return _invalid(e)
    return 200, SummaryResponse(summary=generate_summary(req, app.provider)).model_dump()


def _invalid(e: ValidationError):
    # 입력 값이 에러에 섞이지 않도록 필드 이름만 돌려준다
    fields = sorted({".".join(str(p) for p in err["loc"]) or "body" for err in e.errors()})
    return 422, {"error": "invalid_request", "fields": fields}


def _call(model_cls, body, run):
    """요청 검증 → 실행 → 공통 오류 처리."""
    try:
        req = model_cls.model_validate(body)
    except ValidationError as e:
        return _invalid(e)
    try:
        return 200, run(req).model_dump()
    except UnknownScenario:
        return 404, {"error": "scenario_not_found"}
    except InvalidVariant:
        return 422, {"error": "invalid_variant"}
    except InvalidAxis as e:
        return 422, {"error": "invalid_request", "fields": [e.field]}


def _practice_start(app: App, body):
    """T-12 첫 대사: 시나리오(또는 T-13 변형)의 첫 대사와 상황 설명."""
    return _call(StartRequest, body, lambda r: app.engine.start(r.scenario_id, r.variant))


def _practice_turn(app: App, body):
    """T-12 다음 턴: 아이의 글에 대한 상대 역할의 다음 대사."""
    return _call(TurnRequest, body, app.engine.turn)


def _practice_variant(app: App, body):
    """T-13 단서 고정 변형: 같은 단서, 다른 플랫폼·말투·맥락."""
    return _call(VariantRequest, body, app.variator.generate)


def _practice_judge(app: App, body):
    """T-14 단서 판별: 단서마다 found / missed / not_shown."""
    return _call(JudgeRequest, body, app.judge.judge)


def _practice_feedback(app: App, body):
    """T-14 피드백: 판별 결과를 쉬운 말 문장으로."""
    return _call(FeedbackRequest, body, app.judge.feedback)


# (메서드, 경로) -> (인증 필요 여부, 처리 함수)
ROUTES = {
    ("GET", "/health"): (False, _health),
    ("POST", "/internal/v1/summary"): (True, _summary),
    ("POST", "/internal/v1/practice/start"): (True, _practice_start),
    ("POST", "/internal/v1/practice/turn"): (True, _practice_turn),
    ("POST", "/internal/v1/practice/variant"): (True, _practice_variant),
    ("POST", "/internal/v1/practice/judge"): (True, _practice_judge),
    ("POST", "/internal/v1/practice/feedback"): (True, _practice_feedback),
}


# ---- HTTP 처리 --------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    app: App  # make_server 에서 주입
    server_version = "ai-server"
    sys_version = ""

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def log_message(self, format, *args):  # 기본 로그(요청 줄 전체)는 끈다
        pass

    def _authorized(self) -> bool:
        given = self.headers.get(TOKEN_HEADER, "")
        return hmac.compare_digest(given.encode(), self.app.internal_token.encode())

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise _HttpError(400, "bad_request") from None
        if length <= 0:
            raise _HttpError(400, "invalid_json")
        if length > MAX_BODY_BYTES:
            raise _HttpError(413, "payload_too_large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except ValueError:  # JSONDecodeError, UnicodeDecodeError 포함
            raise _HttpError(400, "invalid_json") from None

    def _dispatch(self, method: str):
        path = self.path.split("?", 1)[0]
        try:
            route = ROUTES.get((method, path))
            if route is None:
                known = any(p == path for (_, p) in ROUTES)
                raise _HttpError(405, "method_not_allowed") if known else _HttpError(404, "not_found")
            needs_auth, handler = route
            if needs_auth and not self._authorized():
                raise _HttpError(401, "unauthorized")
            body = self._read_json() if method == "POST" else None
            status, payload = handler(self.app, body)
        except _HttpError as e:
            status, payload = e.status, {"error": e.code}
        except Exception as e:  # 내용은 로그에 남기지 않고 종류만 남긴다
            log.error("unhandled error: %s", type(e).__name__)
            status, payload = 500, {"error": "internal_error"}

        log.info("%s %s -> %s", method, path, status)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(app: App, host: str = "127.0.0.1", port: int = 8081) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)
