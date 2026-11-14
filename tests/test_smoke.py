"""스모크 테스트: 서버가 뜨고, 인증·검증·로그 규칙이 지켜지는지 확인한다."""
import json
import logging
from pathlib import Path

import pytest

from app.config import Config, ConfigError
from app.providers import FakeProvider

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
SUMMARY_PATH = "/internal/v1/summary"


# ---- health / 인증 ----------------------------------------------------------

def test_health_is_open_without_token(client):
    status, body = client.request("GET", "/health", token=None)
    assert status == 200 and body["status"] == "ok"


def test_internal_api_requires_token(client):
    status, body = client.request("POST", SUMMARY_PATH, {"area": "a", "practice_count": 1}, token=None)
    assert status == 401 and body == {"error": "unauthorized"}


def test_wrong_token_is_rejected(client):
    status, _ = client.request("POST", SUMMARY_PATH, {"area": "a", "practice_count": 1}, token="nope")
    assert status == 401


def test_unknown_path_and_wrong_method(client):
    assert client.request("GET", "/nothing")[0] == 404
    assert client.request("GET", SUMMARY_PATH)[0] == 405


# ---- 계약 샘플 (백엔드와 같은 JSON 으로 테스트, AI-3) -------------------------

def test_summary_contract_sample(start_server):
    request = json.loads((CONTRACTS / "summary.request.json").read_text(encoding="utf-8"))
    expected = json.loads((CONTRACTS / "summary.response.json").read_text(encoding="utf-8"))
    client = start_server(FakeProvider(expected["summary"]))
    status, body = client.request("POST", SUMMARY_PATH, request)
    assert status == 200 and body == expected


# ---- 입력 검증 / 실패 처리 ----------------------------------------------------

def test_invalid_body_returns_422_without_echoing_input(client):
    status, body = client.request("POST", SUMMARY_PATH, {"area": "비밀지역", "practice_count": "abc"})
    assert status == 422
    assert body["fields"] == ["practice_count"]
    assert "비밀지역" not in json.dumps(body, ensure_ascii=False) and "abc" not in json.dumps(body)


def test_broken_json_returns_400(client):
    status, body = client.request("POST", SUMMARY_PATH, raw=b"{not json")
    assert status == 400 and body == {"error": "invalid_json"}


def test_provider_failure_gives_null_summary(start_server):
    class Boom:
        def generate(self, prompt):
            raise RuntimeError("timeout")

    client = start_server(Boom())
    status, body = client.request("POST", SUMMARY_PATH, {"area": "사기", "practice_count": 2})
    assert status == 200 and body == {"summary": None}


# ---- 로그 규칙 (AI-2) -------------------------------------------------------

def test_logs_never_contain_prompt_or_output(start_server, caplog):
    caplog.set_level(logging.DEBUG)
    client = start_server(FakeProvider("비밀출력ABC"))
    status, body = client.request(
        "POST", SUMMARY_PATH, {"area": "사기", "practice_count": 1, "found_clues": ["비밀단서XYZ"]}
    )
    assert status == 200 and body["summary"] == "비밀출력ABC"
    assert "비밀단서XYZ" not in caplog.text
    assert "비밀출력ABC" not in caplog.text
    assert "POST /internal/v1/summary -> 200" in caplog.text


# ---- 환경 변수 --------------------------------------------------------------

def test_config_defaults():
    cfg = Config.from_env({"AI_INTERNAL_TOKEN": "t"})
    assert (cfg.port, cfg.provider, cfg.host) == (8081, "fake", "127.0.0.1")


def test_config_requires_token():
    with pytest.raises(ConfigError):
        Config.from_env({})


def test_config_gemini_requires_key():
    with pytest.raises(ConfigError):
        Config.from_env({"AI_INTERNAL_TOKEN": "t", "AI_PROVIDER": "gemini"})


def test_config_repr_hides_secrets():
    cfg = Config.from_env({"AI_INTERNAL_TOKEN": "supersecret", "AI_PROVIDER": "gemini", "GEMINI_API_KEY": "k-123"})
    assert "supersecret" not in repr(cfg) and "k-123" not in repr(cfg)
