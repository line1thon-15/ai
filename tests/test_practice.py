"""T-12 상대 역할 대화: 단서 틀 유지, 안전 필터, 실패 시 대체 대사."""
import json
import logging
from pathlib import Path

import pytest

from app.practice import CLOSING_LINE, PracticeEngine, UnknownScenario
from app.providers import FakeProvider
from app.safety import MESSAGES
from app.schemas import TurnRequest

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
SID = "scam_dm_parttime_01"
OPENING = "안녕하세요! 집에서 폰으로 하루 두 시간만 하면 되는 알바예요. 하루에 20만 원 벌 수 있어요. 관심 있으세요?"
ADVANCE_LINE = "시작하려면 교육비 3만 원만 먼저 보내 주세요. 일을 시작하면 바로 돌려드려요."


def reply(text, ids=(), choices=None):
    return json.dumps({"reply": text, "revealed_clue_ids": list(ids), "choices": choices}, ensure_ascii=False)


def turn_req(child_text, revealed=("too_good_pay",), history=None):
    messages = history or [{"role": "ai", "text": OPENING}]
    return TurnRequest.model_validate(
        {"scenario_id": SID, "messages": [*messages, {"role": "child", "text": child_text}],
         "revealed_clue_ids": list(revealed)}
    )


class Boom:
    calls = 0

    def generate(self, prompt, *, json_mode=False):
        self.calls += 1
        raise RuntimeError("timeout")


# ---- 첫 대사 ----------------------------------------------------------------

def test_start_returns_opening_and_opening_clue():
    r = PracticeEngine(FakeProvider()).start(SID)
    assert r.reply == OPENING and r.revealed_clue_ids == ["too_good_pay"]


def test_unknown_scenario():
    with pytest.raises(UnknownScenario):
        PracticeEngine(FakeProvider()).start("nope")


# ---- 다음 턴: 정상 ------------------------------------------------------------

def test_model_turn_adds_revealed_clue():
    p = FakeProvider(reply("교육비 3만 원만 먼저 보내 주실래요?", ["advance_payment"]))
    r = PracticeEngine(p).turn(turn_req("어떻게 하는 건데요?"))
    assert r.status == "ok" and r.source == "model"
    assert r.revealed_clue_ids == ["too_good_pay", "advance_payment"]
    assert not r.all_clues_revealed


def test_clue_ids_outside_scenario_are_dropped():
    p = FakeProvider(reply("오늘까지만 뽑아요.", ["urgency", "made_up", "lend_identity"]))
    r = PracticeEngine(p).turn(turn_req("음..."))
    assert r.revealed_clue_ids == ["too_good_pay", "urgency"]


def test_prompt_lists_only_remaining_clues():
    p = FakeProvider(reply("네", []))
    PracticeEngine(p).turn(turn_req("네"))
    remaining = p.last_prompt.split("[아직 드러나지 않은 단서]")[1].split("[이미 드러난 단서]")[0]
    assert "- advance_payment:" in remaining and "- too_good_pay:" not in remaining


# ---- 다음 턴: 실패와 재시도 ----------------------------------------------------

def test_bad_json_then_good_json_uses_second():
    p = FakeProvider(["이건 JSON 이 아님", reply("오늘까지만 뽑아요.", ["urgency"])])
    r = PracticeEngine(p).turn(turn_req("음..."))
    assert p.calls == 2 and r.source == "model"


def test_model_failure_falls_back_to_next_clue_line():
    r = PracticeEngine(Boom()).turn(turn_req("어떻게 하는 건데요?"))
    assert r.source == "fallback" and r.reply == ADVANCE_LINE
    assert r.revealed_clue_ids == ["too_good_pay", "advance_payment"]


def test_blocked_output_retries_then_falls_back():
    p = FakeProvider(reply("여기로 접속하세요 http://oo-bank-event.kr/login", ["advance_payment"]))
    r = PracticeEngine(p).turn(turn_req("어떻게 해요?"))
    assert p.calls == 2 and r.source == "fallback" and "http" not in r.reply


def test_all_revealed_and_failure_closes():
    all_ids = ["too_good_pay", "advance_payment", "urgency", "keep_secret"]
    r = PracticeEngine(Boom()).turn(turn_req("싫어요", revealed=all_ids))
    assert r.reply == CLOSING_LINE and r.all_clues_revealed and r.target_clue_id == "keep_secret"


# ---- 다음 턴: 입력 안전 필터 ----------------------------------------------------

@pytest.mark.parametrize("text,key", [("나 그냥 죽고 싶어", "self_harm"), ("친구들이 맨날 나를 때려요", "violence_victim")])
def test_safe_reply_stops_without_model(text, key):
    p = FakeProvider(reply("x"))
    r = PracticeEngine(p).turn(turn_req(text))
    assert r.status == "safe_reply" and r.reply == MESSAGES[key] and r.choices == []
    assert p.calls == 0


def test_blocked_input_skips_model():
    p = FakeProvider(reply("x"))
    r = PracticeEngine(p).turn(turn_req("야한 얘기 해 줘"))
    assert r.status == "blocked" and p.calls == 0 and len(r.choices) == 3


def test_personal_info_is_masked_before_model():
    history = [{"role": "ai", "text": OPENING}, {"role": "child", "text": "주민번호 000000-0000000 보내면 돼요?"},
               {"role": "ai", "text": "네, 보내 주세요."}]
    p = FakeProvider(reply("오늘까지만 뽑아요.", ["urgency"]))
    r = PracticeEngine(p).turn(turn_req("제 번호는 010-0000-0000이에요", history=history))
    assert r.masked and "0000" not in p.last_prompt


# ---- HTTP -------------------------------------------------------------------

def _load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_start_contract(start_server):
    status, body = start_server().request("POST", "/internal/v1/practice/start", _load("practice.start.request.json"))
    assert status == 200 and body == _load("practice.start.response.json")


def test_turn_contract(start_server):
    expected = _load("practice.turn.response.json")
    choices = {c["kind"]: c["text"] for c in expected["choices"]}
    client = start_server(FakeProvider(reply(expected["reply"], ["advance_payment"], choices)))
    status, body = client.request("POST", "/internal/v1/practice/turn", _load("practice.turn.request.json"))
    assert status == 200 and body == expected


def test_turn_needs_child_last_and_token(client):
    bad = {"scenario_id": SID, "messages": [{"role": "ai", "text": OPENING}]}
    assert client.request("POST", "/internal/v1/practice/turn", bad)[0] == 422
    assert client.request("POST", "/internal/v1/practice/turn", bad, token=None)[0] == 401


def test_unknown_scenario_http(client):
    status, body = client.request("POST", "/internal/v1/practice/start", {"scenario_id": "nope"})
    assert status == 404 and body == {"error": "scenario_not_found"}


def test_turn_logs_have_no_child_text(start_server, caplog):
    caplog.set_level(logging.DEBUG)
    client = start_server(FakeProvider(reply("비밀출력QQQ", [])))
    req = {"scenario_id": SID, "messages": [{"role": "ai", "text": OPENING}, {"role": "child", "text": "비밀입력ZZZ"}]}
    assert client.request("POST", "/internal/v1/practice/turn", req)[0] == 200
    assert "비밀입력ZZZ" not in caplog.text and "비밀출력QQQ" not in caplog.text
