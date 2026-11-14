"""T-74 힌트: 백엔드가 정한 단계(0~3)에 맞는 문장을 start·turn 응답에 넣는다."""
import json

import pytest

from app.content import load_all_scenarios, load_clues
from app.hints import GENERIC_HINTS, NORMAL_HINTS, hint_text
from app.practice import PracticeEngine
from app.providers import FakeProvider
from app.safety import check_output
from app.schemas import TurnRequest

SCENARIOS = load_all_scenarios()
CLUES = load_clues()["clues"]
SID = "scam_dm_parttime_01"
OPENING = SCENARIOS[SID]["opening_line"]


def test_level_zero_gives_no_hint():
    assert hint_text(SCENARIOS[SID], "advance_payment", 0) is None
    assert PracticeEngine(FakeProvider()).start(SID).hint is None


@pytest.mark.parametrize("level", [1, 2, 3])
def test_start_hint_matches_opening_clue(level):
    r = PracticeEngine(FakeProvider()).start(SID, hint_level=level)
    assert r.hint == hint_text(SCENARIOS[SID], "too_good_pay", level)


def test_levels_get_more_specific():
    h1, h2, h3 = (hint_text(SCENARIOS[SID], "advance_payment", lv) for lv in (1, 2, 3))
    assert "먼저 돈을 내라고 해요" not in h1 and "돈" in h2 and "'먼저 돈을 내라고 해요'" in h3


def test_turn_hint_follows_target_clue():
    reply = json.dumps({"reply": "교육비 3만 원만 먼저 보내 주세요.", "revealed_clue_ids": ["advance_payment"]}, ensure_ascii=False)
    req = TurnRequest.model_validate({"scenario_id": SID, "hint_level": 2, "revealed_clue_ids": ["too_good_pay"],
                                     "messages": [{"role": "ai", "text": OPENING}, {"role": "child", "text": "네"}]})
    r = PracticeEngine(FakeProvider(reply)).turn(req)
    assert r.target_clue_id == "advance_payment" and r.hint == hint_text(SCENARIOS[SID], "advance_payment", 2)


def test_safe_reply_has_no_hint():
    req = TurnRequest.model_validate({"scenario_id": SID, "hint_level": 3,
                                     "messages": [{"role": "child", "text": "나 그냥 죽고 싶어"}]})
    assert PracticeEngine(FakeProvider()).turn(req).hint is None


def test_normal_situation_hint():
    assert PracticeEngine(FakeProvider()).start("normal_cafe_01", hint_level=1).hint == NORMAL_HINTS[1]


def test_hint_level_out_of_range_is_rejected(client):
    assert client.request("POST", "/internal/v1/practice/start", {"scenario_id": SID, "hint_level": 4})[0] == 422


def all_hints():
    for c in CLUES:
        yield from c["hints"].values()
        yield f"'{c['name']}' 신호예요. {c['safe_action']}."
    yield from NORMAL_HINTS.values()
    yield from GENERIC_HINTS.values()


@pytest.mark.parametrize("text", list(all_hints()))
def test_hints_pass_feedback_filter(text):
    assert check_output(text, "feedback").allowed and len(text) <= 80
