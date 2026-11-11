"""T-78 심화 연습 피드백: 아이가 쓴 판단 이유에 1~3문장, 점수 없음, 입·출력 안전 필터."""
import json
import logging

import pytest

from app.content import load_all_scenarios
from app.deep import DeepCoach, sentence_problem, template
from app.providers import FakeProvider
from app.safety import MESSAGES
from app.scenarios import CLUE_DEFS
from app.schemas import DeepFeedbackRequest

SCENARIOS = load_all_scenarios()
SID = "scam_dm_parttime_01"
ANSWER = "일하기 전에 돈을 먼저 보내라고 해서 이상하다고 생각했어요."
GOOD = ["돈을 먼저 내라는 말을 이상하다고 본 건 정말 잘했어요.",
        "오늘까지만 뽑는다고 재촉하는 말도 위험 신호예요.",
        "이럴 때는 바로 정하지 말고 믿는 어른에게 물어봐요."]


def reply(items):
    return json.dumps({"feedback": items}, ensure_ascii=False)


def req(**kw):
    return DeepFeedbackRequest.model_validate({"scenario_id": SID, "answer": ANSWER,
                                               "clue_ids": ["advance_payment", "urgency"], **kw})


class Boom:
    def generate(self, prompt, *, json_mode=False):
        raise RuntimeError


def test_model_feedback_is_used():
    p = FakeProvider(reply(GOOD))
    r = DeepCoach(p).feedback(req(question="왜 그렇게 생각했나요?"))
    assert r.status == "ok" and r.source == "model" and r.feedback == GOOD
    assert "왜 그렇게 생각했나요?" in p.last_prompt and "먼저 돈을 내라고 해요" in p.last_prompt
    assert "비밀 유지" not in p.last_prompt  # 고른 단서만


@pytest.mark.parametrize("bad", [
    ["정답이에요! 잘했어요."],                 # 평가하는 말
    ["3개 중에 2개를 맞혔어요."],               # 숫자
    ["그것도 모르니? 바보 같아요."],             # 비난
    [],                                        # 비어 있음
    "그냥 글",                                  # JSON 아님
])
def test_bad_model_output_falls_back(bad):
    raw = bad if isinstance(bad, str) else reply(bad)
    r = DeepCoach(FakeProvider(raw)).feedback(req())
    assert r.source == "fallback" and r.feedback == template(SCENARIOS[SID], [CLUE_DEFS["advance_payment"],
                                                                                CLUE_DEFS["urgency"]], ANSWER)


def test_more_than_three_sentences_are_cut():
    r = DeepCoach(FakeProvider(reply(GOOD + ["하나 더 있어요."]))).feedback(req())
    assert r.feedback == GOOD


@pytest.mark.parametrize("text,key", [("나 그냥 죽고 싶어", "self_harm"), ("친구들이 맨날 나를 때려요", "violence_victim")])
def test_safe_reply_without_model(text, key):
    p = FakeProvider(reply(GOOD))
    r = DeepCoach(p).feedback(req(answer=text))
    assert r.status == "safe_reply" and r.feedback == [MESSAGES[key]] and p.calls == 0


def test_blocked_answer():
    p = FakeProvider(reply(GOOD))
    r = DeepCoach(p).feedback(req(answer="야한 얘기 해 줘"))
    assert r.status == "blocked" and p.calls == 0


def test_personal_info_masked_before_model():
    p = FakeProvider(reply(GOOD))
    r = DeepCoach(p).feedback(req(answer="제 번호 010-0000-0000 주려다가 이상해서 안 줬어요."))
    assert r.masked and "0000" not in p.last_prompt


def test_normal_situation_template():
    r = DeepCoach(Boom()).feedback(DeepFeedbackRequest(scenario_id="normal_cafe_01", answer="부모님이랑 오라고 해서 괜찮아요."))
    assert r.source == "fallback" and "직접 만나서 이야기해요" in r.feedback[1]


@pytest.mark.parametrize("sid", [k for k, v in SCENARIOS.items() if v["kind"] == "risk"])
def test_templates_pass_rules(sid):
    s = SCENARIOS[sid]
    for c in s["clues"]:
        for sentence in template(s, [CLUE_DEFS[c["id"]]]):
            assert sentence_problem(sentence) is None, sentence


def test_http_and_logs(start_server, caplog):
    caplog.set_level(logging.DEBUG)
    client = start_server(FakeProvider(reply(GOOD)))
    status, body = client.request("POST", "/internal/v1/practice/deep/feedback",
                                  {"scenario_id": SID, "answer": "비밀입력ZZZ 때문에 이상했어요."})
    assert status == 200 and body["feedback"] == GOOD
    assert "비밀입력ZZZ" not in caplog.text
    assert client.request("POST", "/internal/v1/practice/deep/feedback", {"scenario_id": SID, "answer": ""})[0] == 422



def test_fallback_points_to_clue_child_did_not_mention():
    """아이는 '먼저 돈'만 말했으니 대체 문장은 '재촉' 단서를 짚는다."""
    r = DeepCoach(Boom()).feedback(req())
    assert "'빨리 정하라고 재촉해요'" in r.feedback[1]


def test_prompt_requires_pointing_out_a_missed_clue():
    p = FakeProvider(reply(GOOD))
    DeepCoach(p).feedback(req())
    assert "반드시 짚어 줘" in p.last_prompt
