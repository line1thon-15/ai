"""정상 상황 출제·판정 + 한 턴에 새 단서 1개 규칙."""
import json
from pathlib import Path

import pytest

from app.choices import KINDS, NORMAL_GENERIC, validate_texts
from app.content import load_all_scenarios
from app.judge import Judge
from app.practice import NORMAL_FALLBACK, PracticeEngine, shorten
from app.providers import FakeProvider
from app.scenarios import InvalidVariant, base_as_variant
from app.schemas import JudgeRequest, TurnRequest, VariantRequest
from app.variation import Variator

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
SCENARIOS = load_all_scenarios()
NORMAL_IDS = [k for k, v in SCENARIOS.items() if v["kind"] == "normal"]
NID = "normal_cafe_01"
SID = "scam_dm_parttime_01"


def load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


class Boom:
    def generate(self, prompt, *, json_mode=False):
        raise RuntimeError


# ---- 정상 상황: 출제 -----------------------------------------------------------

def test_normal_situations_are_registered():
    assert len(NORMAL_IDS) == 8
    for nid in NORMAL_IDS:
        n = SCENARIOS[nid]
        assert n["clues"] == [] and n["ai_role"]["name"] and n["child_setup"] and n["base_scenario_id"]


@pytest.mark.parametrize("nid", NORMAL_IDS)
def test_normal_start(nid):
    r = PracticeEngine(FakeProvider()).start(nid)
    assert r.reply == SCENARIOS[nid]["opening_line"] and r.revealed_clue_ids == [] and r.target_clue_id is None
    assert sorted(c.kind for c in r.choices) == sorted(KINDS)
    assert {c.text for c in r.choices} == set(NORMAL_GENERIC.values())


def test_normal_start_contract(start_server):
    status, body = start_server().request("POST", "/internal/v1/practice/start", load("practice.normal.start.request.json"))
    assert status == 200 and body == load("practice.normal.start.response.json")


def test_normal_generic_choices_pass_rules():
    assert validate_texts(NORMAL_GENERIC) == NORMAL_GENERIC


def normal_turn(provider, child="좋아요! 그럼 그렇게 할게요."):
    req = TurnRequest.model_validate({"scenario_id": NID, "messages": [
        {"role": "ai", "text": SCENARIOS[NID]["opening_line"]},
        {"role": "child", "text": child, "choice_kind": "other"}]})
    return PracticeEngine(provider), PracticeEngine(provider).turn(req)


def test_normal_turn_with_model():
    choices = {"correct": "이거 수상해요. 안 갈래요.", "doubtful": "괜찮을까요… 조금 걱정돼요.", "other": "네, 토요일에 갈게요!"}
    p = FakeProvider(json.dumps({"reply": "좋아요. 토요일 오후에 부모님이랑 같이 오세요.", "revealed_clue_ids": ["advance_payment"],
                                 "choices": choices}, ensure_ascii=False))
    _, r = normal_turn(p)
    assert r.source == "model" and r.choices_source == "model"
    assert r.revealed_clue_ids == [] and r.target_clue_id is None and r.all_clues_revealed is False
    assert "정상 상황" in p.last_prompt and "[아직 드러나지 않은 단서]" not in p.last_prompt


def test_normal_turn_fallback():
    _, r = normal_turn(Boom())
    assert r.source == "fallback" and r.reply == NORMAL_FALLBACK and r.choices_source == "template"
    assert {c.text for c in r.choices} == set(NORMAL_GENERIC.values())


# ---- T-34 정상 상황 생성 ------------------------------------------------------

NORMAL_VARIANT = {"title": "학교 앞 분식집 주말 알바", "child_setup": "친구 소개로 학교 앞 분식집 사장님이 주말 알바를 제안해요.",
                  "ai_role": {"name": "분식집 사장님", "persona": "친절하고 차분한 사장님. 부모님과 함께 오라고 한다."},
                  "opening_line": "안녕하세요, 주말에 가게 일을 도와줄 사람을 찾고 있어요. 부모님과 같이 가게에 와서 이야기해요."}


def test_normal_variant_from_model():
    r = Variator(FakeProvider(json.dumps(NORMAL_VARIANT, ensure_ascii=False))).generate(
        VariantRequest(scenario_id=NID))
    assert r.source == "model" and r.variant.clues == [] and r.variant.title == NORMAL_VARIANT["title"]
    assert r.variant.platform == SCENARIOS[NID]["platform"]  # 원래 플랫폼 유지
    s = PracticeEngine(FakeProvider()).start(NID, r.variant)
    assert s.reply == NORMAL_VARIANT["opening_line"] and s.revealed_clue_ids == []


@pytest.mark.parametrize("field,bad", [
    ("opening_line", "주말 알바예요. 먼저 교육비를 입금해 주세요."),
    ("opening_line", "오늘까지만 뽑아요. 빨리 정해요."),
    ("child_setup", "사장님이 비밀로 하라고 해요."),
])
def test_normal_variant_with_risk_falls_back(field, bad):
    r = Variator(FakeProvider(json.dumps({**NORMAL_VARIANT, field: bad}, ensure_ascii=False))).generate(
        VariantRequest(scenario_id=NID))
    assert r.source == "fallback" and r.variant.opening_line == SCENARIOS[NID]["opening_line"]


@pytest.mark.parametrize("nid", NORMAL_IDS)
def test_normal_originals_pass_their_own_check(nid):
    """대체용 원본이 검사에 걸리면 안 된다 (예: '비밀번호를 절대 묻지 않아요')."""
    from app.scenarios import check_variant
    assert check_variant(SCENARIOS[nid], base_as_variant(SCENARIOS[nid])) == []


def test_risk_variant_cannot_be_used_for_normal():
    with pytest.raises(InvalidVariant):
        PracticeEngine(FakeProvider()).start(NID, base_as_variant(SCENARIOS[SID]))


# ---- T-34 정상 상황 판정 문구 ---------------------------------------------------

@pytest.mark.parametrize("outcome", ["trusted_correctly", "over_warned"])
def test_normal_feedback_fallback(outcome):
    from app.judge import normal_template
    from app.schemas import FeedbackRequest
    r = Judge(Boom()).feedback(FeedbackRequest(scenario_id=NID, normal_outcome=outcome))
    assert r.source == "fallback" and r.normal_feedback == normal_template(SCENARIOS[NID], outcome)
    assert "직접 만나서 이야기해요" in r.normal_feedback


def test_normal_feedback_from_model():
    from app.schemas import FeedbackRequest
    text = "카페 사장님이 부모님과 함께 오라고 한 걸 잘 봤어요. 믿어도 되는 상황을 잘 알아봤어요."
    p = FakeProvider(json.dumps({"feedback": text}, ensure_ascii=False))
    r = Judge(p).feedback(FeedbackRequest(scenario_id=NID, normal_outcome="trusted_correctly"))
    assert r.source == "model" and r.normal_feedback == text and "지나치게" not in p.last_prompt.split("[결과]")[1][:40]


def test_normal_feedback_blame_rejected():
    from app.schemas import FeedbackRequest
    p = FakeProvider(json.dumps({"feedback": "그것도 모르니? 바보 같아요."}, ensure_ascii=False))
    r = Judge(p).feedback(FeedbackRequest(scenario_id=NID, normal_outcome="over_warned"))
    assert r.source == "fallback" and "바보" not in r.normal_feedback


@pytest.mark.parametrize("nid", NORMAL_IDS)
def test_normal_templates_pass_filter(nid):
    from app.judge import feedback_problem, normal_template
    for outcome in ("trusted_correctly", "over_warned"):
        assert feedback_problem(normal_template(SCENARIOS[nid], outcome)) is None


# ---- 정상 상황: 판정 -----------------------------------------------------------

def judge(kinds):
    msgs = [{"role": "ai", "text": "안녕하세요"}]
    msgs += [{"role": "child", "text": f"답 {i}", "choice_kind": k} for i, k in enumerate(kinds)]
    return Judge(FakeProvider()).judge(JudgeRequest.model_validate({"scenario_id": NID, "messages": msgs}))


@pytest.mark.parametrize("kinds,outcome", [
    (["other"], "trusted_correctly"),
    (["doubtful", "other"], "trusted_correctly"),
    (["other", "correct"], "over_warned"),   # 한 번이라도 의심·거절하면
    (["correct"], "over_warned"),
])
def test_normal_outcome(kinds, outcome):
    r = judge(kinds)
    assert r.normal_outcome == outcome and r.results == [] and r.source == "choices"


def test_normal_without_choices_has_no_outcome():
    r = Judge(FakeProvider()).judge(JudgeRequest.model_validate(
        {"scenario_id": NID, "messages": [{"role": "child", "text": "네"}]}))
    assert r.normal_outcome is None and r.source == "fixed"


def test_normal_judge_contract(start_server):
    status, body = start_server().request("POST", "/internal/v1/practice/judge", load("practice.normal.judge.request.json"))
    assert status == 200 and body == load("practice.normal.judge.response.json")
    assert body["normal_outcome"] == "trusted_correctly"


def test_risk_judge_has_null_outcome():
    r = Judge(FakeProvider()).judge(JudgeRequest.model_validate(load("practice.judge.request.json")))
    assert r.normal_outcome is None


def test_normal_feedback_with_empty_results(start_server):
    status, body = start_server().request("POST", "/internal/v1/practice/feedback", {"scenario_id": NID, "results": []})
    assert status == 200 and body["cards"] == [] and body["source"] == "fixed"


# ---- 위험 상황: 한 턴에 새 단서 1개 ----------------------------------------------

OPENING = SCENARIOS[SID]["opening_line"]


def risk_turn(reply, ids):
    p = FakeProvider([json.dumps({"reply": reply, "revealed_clue_ids": ids}, ensure_ascii=False)] * 2)
    req = TurnRequest.model_validate({"scenario_id": SID, "revealed_clue_ids": ["too_good_pay"], "messages": [
        {"role": "ai", "text": OPENING}, {"role": "child", "text": "어떻게 해요?"}]})
    return p, PracticeEngine(p).turn(req)


def test_two_clues_in_separate_sentences_keep_only_first():
    p, r = risk_turn("시작하려면 교육비 3만 원만 먼저 입금해 주세요. 부모님께는 비밀로 해 주세요.",
                     ["advance_payment", "keep_secret"])
    assert r.source == "model" and r.revealed_clue_ids == ["too_good_pay", "advance_payment"]
    assert "비밀" not in r.reply and r.target_clue_id == "advance_payment"


def test_two_clues_in_one_sentence_is_rejected():
    p, r = risk_turn("교육비는 부모님께 비밀로 하고 먼저 입금해 주세요.", ["advance_payment", "keep_secret"])
    assert p.calls == 2 and r.source == "fallback"
    assert r.revealed_clue_ids == ["too_good_pay", "advance_payment"]  # 대체 대사도 단서 1개


def test_shorten_rules():
    assert shorten("하나예요. 둘이에요.", []) == "하나예요. 둘이에요."
    assert shorten("교육비를 보내 주세요. 비밀이에요.", ["advance_payment"], ["keep_secret"]) == "교육비를 보내 주세요."
    assert shorten("비밀이에요.", ["advance_payment"], ["keep_secret"]) is None


def test_shorten_drops_leading_connective_when_first_sentence_removed():
    # 실제 Gemini 출력 (2026-11-12 로컬 확인)
    full = "네, 좋아요! 그런데 저희가 오늘까지만 사람을 뽑고 있거든요. 지금 바로 시작할 수 있는지 알려주셔야 해요!"
    assert shorten(full, ["urgency"]) == "저희가 오늘까지만 사람을 뽑고 있거든요. 지금 바로 시작할 수 있는지 알려주셔야 해요!"
    # 첫 문장을 남기면 접속어는 그대로
    assert shorten("그런데 오늘만 해요. 둘이에요. 셋이에요.", ["urgency"]) == "그런데 오늘만 해요. 둘이에요."



# ---- Gemini 확인 결과 반영 (2026-11-12) -----------------------------------------

def test_normal_variant_cannot_move_to_stranger_platform():
    """'아는 사람 소개'가 '오픈채팅의 모르는 사람'이 되면 위험 상황과 같아진다."""
    from app.variation import InvalidAxis
    with pytest.raises(InvalidAxis):
        Variator(FakeProvider("x")).generate(VariantRequest(scenario_id=NID, platform="open_chat"))
    p = FakeProvider("x")
    Variator(p).generate(VariantRequest(scenario_id=NID, favorite_apps=["인스타"]))
    assert "아는 사람의 소개" in p.last_prompt and "바꾸지 마" in p.last_prompt


def test_normal_variant_with_stranger_wording_falls_back():
    # 실제 Gemini 출력 (2026-11-12 로컬 확인)
    bad = {**NORMAL_VARIANT, "title": "오픈채팅방에 뜬 알바 모집 글"}
    r = Variator(FakeProvider(json.dumps(bad, ensure_ascii=False))).generate(VariantRequest(scenario_id=NID))
    assert r.source == "fallback"
