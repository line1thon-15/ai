"""T-14 단서 판별 + 피드백."""
import json
from pathlib import Path

import pytest

from app.content import load_clues
from app.judge import DEFAULT_CLOSING, Judge, heuristic_found, template
from app.providers import FakeProvider
from app.safety import check_output
from app.schemas import ClueResult, FeedbackRequest, JudgeRequest

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
SID = "scam_dm_parttime_01"


def load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


JUDGE_REQ = load("practice.judge.request.json")
FEEDBACK_REQ = load("practice.feedback.request.json")
FEEDBACK_RES = load("practice.feedback.response.json")


class Boom:
    calls = 0

    def generate(self, prompt, *, json_mode=False):
        self.calls += 1
        raise RuntimeError


def judge_reply(**results):
    return json.dumps({"results": [{"clue_id": k, "result": v} for k, v in results.items()]})


# ---- 판별 -------------------------------------------------------------------

# 글로 쓴 답(선택지 정보 없음)으로 바꾼 요청: 모델 판정 경로
FREE_REQ = {**JUDGE_REQ, "messages": [{"role": m["role"], "text": m["text"]} for m in JUDGE_REQ["messages"]]}


def test_judge_by_choices_matches_contract_without_model():
    p = FakeProvider("x")
    r = Judge(p).judge(JudgeRequest.model_validate(JUDGE_REQ))
    assert r.model_dump() == load("practice.judge.response.json") and p.calls == 0


def test_judge_doubtful_choice_is_missed():
    msgs = [*JUDGE_REQ["messages"][:3],
            {"role": "child", "text": "돌려준다고 하니까… 일단 보내 볼까요?", "choice_kind": "doubtful",
             "clue_id": "advance_payment"}]
    r = Judge(FakeProvider("x")).judge(JudgeRequest.model_validate({**JUDGE_REQ, "messages": msgs}))
    assert {x.clue_id: x.result for x in r.results}["advance_payment"] == "missed"


def test_judge_model_result_for_free_text():
    p = FakeProvider(judge_reply(too_good_pay="missed", advance_payment="found"))
    r = Judge(p).judge(JudgeRequest.model_validate(FREE_REQ))
    assert r.source == "model"
    assert [x.result for x in r.results] == ["missed", "found", "not_shown", "not_shown"]
    # 판별 대상은 드러난 단서만
    assert "- advance_payment:" in p.last_prompt and "- urgency:" not in p.last_prompt


@pytest.mark.parametrize("bad", [
    judge_reply(too_good_pay="found"),                                         # 하나 빠짐
    judge_reply(too_good_pay="found", advance_payment="maybe"),                # 이상한 값
    judge_reply(too_good_pay="found", advance_payment="found", urgency="found"),  # 안 드러난 단서
    "점수는 80점",                                                              # JSON 아님
])
def test_judge_invalid_model_output_falls_back(bad):
    r = Judge(FakeProvider(bad)).judge(JudgeRequest.model_validate(FREE_REQ))
    assert r.source == "fallback"
    assert {x.clue_id: x.result for x in r.results}["advance_payment"] == "found"


def test_judge_nothing_revealed_skips_model():
    p = FakeProvider("x")
    r = Judge(p).judge(JudgeRequest.model_validate({**JUDGE_REQ, "revealed_clue_ids": []}))
    assert r.source == "fixed" and p.calls == 0 and {x.result for x in r.results} == {"not_shown"}


def test_judge_masks_child_pii():
    req = {**FREE_REQ, "messages": [*FREE_REQ["messages"], {"role": "child", "text": "제 번호는 010-0000-0000"}]}
    p = FakeProvider(judge_reply(too_good_pay="missed", advance_payment="found"))
    Judge(p).judge(JudgeRequest.model_validate(req))
    assert "0000" not in p.last_prompt


@pytest.mark.parametrize("clue,text,expected", [
    ("advance_payment", "돈을 먼저 보내는 건 이상해요", True),
    ("advance_payment", "네 지금 보낼게요", False),
    ("suspicious_link", "링크는 안 누를래요", True),
    ("suspicious_link", "눌러 볼게요", False),
    ("keep_secret", "엄마한테 물어볼게요", True),
    ("personal_info", "제 계좌 알려 드릴게요", False),
])
def test_heuristic(clue, text, expected):
    assert heuristic_found(clue, [text]) is expected


# ---- 피드백 -----------------------------------------------------------------

def feedback_reply(res=FEEDBACK_RES, **override):
    data = {"cards": [{"clue_id": c["clue_id"], "text": c["text"]} for c in res["cards"]],
            "closing_line": res["closing_line"]}
    data.update(override)
    return json.dumps(data, ensure_ascii=False)


def test_feedback_model_matches_contract():
    r = Judge(FakeProvider(feedback_reply())).feedback(FeedbackRequest.model_validate(FEEDBACK_REQ))
    assert r.model_dump() == FEEDBACK_RES


def test_feedback_skips_not_shown_and_unknown():
    req = {**FEEDBACK_REQ, "results": [*FEEDBACK_REQ["results"], {"clue_id": "lend_identity", "result": "found"}]}
    r = Judge(FakeProvider(feedback_reply())).feedback(FeedbackRequest.model_validate(req))
    assert [c.clue_id for c in r.cards] == ["too_good_pay", "advance_payment"]


def test_feedback_bad_card_replaced_by_template():
    cards = [{"clue_id": "too_good_pay", "text": "점수는 40점이에요."},  # 숫자·점수
             {"clue_id": "advance_payment", "text": FEEDBACK_RES["cards"][1]["text"]}]
    r = Judge(FakeProvider(feedback_reply(cards=cards))).feedback(FeedbackRequest.model_validate(FEEDBACK_REQ))
    assert r.source == "mixed"
    assert r.cards[0].text == template(ClueResult(clue_id="too_good_pay", result="missed"))
    assert r.cards[1].text == FEEDBACK_RES["cards"][1]["text"]


def test_feedback_blame_is_rejected():
    cards = [{"clue_id": "too_good_pay", "text": "그것도 모르니? 바보 같아요."},
             {"clue_id": "advance_payment", "text": "잘했어요."}]
    r = Judge(FakeProvider(feedback_reply(cards=cards))).feedback(FeedbackRequest.model_validate(FEEDBACK_REQ))
    assert "바보" not in r.cards[0].text


def test_feedback_model_failure_uses_templates():
    b = Boom()
    r = Judge(b).feedback(FeedbackRequest.model_validate(FEEDBACK_REQ))
    assert r.source == "fallback" and r.closing_line == DEFAULT_CLOSING and b.calls == 2
    assert all(c.text == template(ClueResult(clue_id=c.clue_id, result=c.result)) for c in r.cards)


def test_feedback_nothing_to_say():
    req = {**FEEDBACK_REQ, "results": [{"clue_id": "urgency", "result": "not_shown"}]}
    r = Judge(FakeProvider("x")).feedback(FeedbackRequest.model_validate(req))
    assert r.cards == [] and r.source == "fixed"


@pytest.mark.parametrize("clue", [c["id"] for c in load_clues()["clues"]])
@pytest.mark.parametrize("result", ["found", "missed"])
def test_templates_pass_feedback_filter(clue, result):
    assert check_output(template(ClueResult(clue_id=clue, result=result)), "feedback").allowed


# ---- HTTP -------------------------------------------------------------------

def test_judge_and_feedback_http(start_server):
    client = start_server(FakeProvider([judge_reply(too_good_pay="missed", advance_payment="found"), feedback_reply()]))
    status, judged = client.request("POST", "/internal/v1/practice/judge", JUDGE_REQ)
    assert status == 200 and judged == load("practice.judge.response.json")  # 선택 기록 판정
    status, fb = client.request("POST", "/internal/v1/practice/feedback",
                                {"scenario_id": SID, "results": judged["results"]})
    assert status == 200 and fb == FEEDBACK_RES
