"""P1 기능(T-74, T-32, T-34, T-78)의 계약 샘플이 서버 응답과 같은지 확인한다."""
import json
from pathlib import Path

from app.providers import FakeProvider

C = Path(__file__).resolve().parent.parent / "contracts"


def load(name):
    return json.loads((C / name).read_text(encoding="utf-8"))


def test_start_with_hint(start_server):
    status, body = start_server().request("POST", "/internal/v1/practice/start", load("practice.start.hint.request.json"))
    assert status == 200 and body == load("practice.start.hint.response.json") and body["hint"]


def test_setup(start_server):
    status, body = start_server().request("POST", "/internal/v1/practice/setup", load("practice.setup.request.json"))
    assert status == 200 and body == load("practice.setup.response.json")


def test_normal_variant(start_server):
    v = load("practice.normal.variant.response.json")["variant"]
    model = {k: v[k] for k in ("title", "child_setup", "opening_line")}
    model["ai_role"] = {"name": v["ai_role"]["name"], "persona": v["ai_role"]["persona"]}
    client = start_server(FakeProvider(json.dumps(model, ensure_ascii=False)))
    status, body = client.request("POST", "/internal/v1/practice/variant", load("practice.normal.variant.request.json"))
    assert status == 200 and body == load("practice.normal.variant.response.json")


def test_normal_feedback(start_server):
    expected = load("practice.normal.feedback.response.json")
    client = start_server(FakeProvider(json.dumps({"feedback": expected["normal_feedback"]}, ensure_ascii=False)))
    status, body = client.request("POST", "/internal/v1/practice/feedback", load("practice.normal.feedback.request.json"))
    assert status == 200 and body == expected


def test_deep_feedback(start_server):
    expected = load("practice.deep.feedback.response.json")
    client = start_server(FakeProvider(json.dumps({"feedback": expected["feedback"]}, ensure_ascii=False)))
    status, body = client.request("POST", "/internal/v1/practice/deep/feedback", load("practice.deep.feedback.request.json"))
    assert status == 200 and body == expected
