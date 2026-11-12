"""T-34 회귀 테스트: 실제 Gemini 출력에서 나온 '상황과 맞지 않는 정상 상황'이 다시 통과하지 않는지 확인한다.

사례 1 (normal_cafe_01 변형): 동네 카페 사장님 → '옆집 누나의 과외 제안', 첫 대사 '… 우리 집으로 놀러 와'.
  상대 관계와 만나는 곳이 바뀌어 안심 신호(직접 가게에서, 부모님과 함께)가 무너졌다.
사례 2 (normal_cafe_01 판정 문구): '모르는 사람을 조심하는 마음은 아주 중요해요…'.
  상대는 아는 사람의 소개로 연락한 카페 사장님이라 상황과 맞지 않는다.
"""
import json

import pytest

from app.content import load_all_scenarios
from app.judge import Judge, normal_feedback_problem
from app.practice import PracticeEngine
from app.providers import FakeProvider
from app.scenarios import base_as_variant, check_variant
from app.schemas import FeedbackRequest, Message, TurnRequest, VariantRequest
from app.variation import Variator

S = load_all_scenarios()
CAFE = S["normal_cafe_01"]

# 실제 출력 (변형)
NEIGHBOR = {
    "title": "옆집 누나의 과외 제안",
    "child_setup": "옆집에 사는 누나가 공부를 봐 주겠다고 연락했어요.",
    "ai_role": {"name": "옆집 누나", "persona": "친절한 대학생 누나."},
    "opening_line": "안녕! 주말에 공부 좀 봐 줄게. 우리 집으로 놀러 와.",
}
# 실제 출력 (판정 문구)
STRANGER_FEEDBACK = "모르는 사람을 조심하는 마음은 아주 중요해요. 다음에도 그렇게 조심해요."


def _variant(data):
    v = base_as_variant(CAFE).model_dump()
    v.update(title=data["title"], child_setup=data["child_setup"], opening_line=data["opening_line"])
    v["ai_role"].update(data["ai_role"])
    from app.schemas import Variant
    return Variant(**v)


def test_neighbor_variant_rejected():
    problems = check_variant(CAFE, _variant(NEIGHBOR))
    assert any(p.startswith("keep_missing") for p in problems)
    assert any(p.startswith("risk_phrase") for p in problems)  # '우리 집', '놀러 와'
    assert any(p.startswith("signal_missing") for p in problems)  # '부모님과 함께'가 사라짐


def test_neighbor_variant_falls_back_to_original():
    p = FakeProvider(json.dumps(NEIGHBOR, ensure_ascii=False))
    res = Variator(p, S).generate(VariantRequest(scenario_id="normal_cafe_01"))
    assert res.source == "fallback"
    assert res.variant.title == CAFE["title"] and res.variant.opening_line == CAFE["opening_line"]
    assert p.calls == 2  # 1번 다시 만들어 보고 원본으로


def test_neighbor_variant_rejected_when_sent_back():
    # 백엔드가 이런 변형을 그대로 보내도 연습에 쓰지 않는다
    with pytest.raises(Exception):
        PracticeEngine(FakeProvider("x")).start("normal_cafe_01", _variant(NEIGHBOR))


def test_same_relation_other_shop_passes():
    ok = {
        "title": "학교 앞 분식집 주말 알바",
        "child_setup": "아는 사람 소개로 분식집 사장님이 주말 알바를 제안해요.",
        "ai_role": {"name": "분식집 사장님", "persona": "차분한 사장님."},
        "opening_line": "주말 알바를 구해요. 부모님과 같이 가게에 와서 이야기해요.",
    }
    assert check_variant(CAFE, _variant(ok)) == []


def test_stranger_feedback_rejected():
    assert normal_feedback_problem(CAFE, STRANGER_FEEDBACK) is not None


@pytest.mark.parametrize("outcome", ["over_warned", "trusted_correctly"])
def test_stranger_feedback_falls_back(outcome):
    p = FakeProvider(json.dumps({"feedback": STRANGER_FEEDBACK}, ensure_ascii=False))
    res = Judge(p, S).feedback(FeedbackRequest(scenario_id="normal_cafe_01", normal_outcome=outcome))
    assert res.source == "fallback"
    assert "모르는 사람" not in res.normal_feedback
    assert normal_feedback_problem(CAFE, res.normal_feedback) is None


def test_feedback_without_safe_signal_rejected():
    assert normal_feedback_problem(CAFE, "조심하는 마음은 좋아요. 다음에도 잘 생각해 봐요.") == "no_safe_signal"


def test_feedback_with_safe_signal_passes():
    text = "조심하는 마음은 좋아요. 그런데 사장님이 부모님과 함께 오라고 했으니 믿어도 되는 상황이었어요."
    assert normal_feedback_problem(CAFE, text) is None


@pytest.mark.parametrize("nid", [k for k, s in S.items() if s.get("kind") == "normal"])
def test_templates_and_originals_pass_new_checks(nid):
    s = S[nid]
    assert check_variant(s, base_as_variant(s)) == []
    for outcome in ("over_warned", "trusted_correctly"):
        from app.judge import normal_template
        assert normal_feedback_problem(s, normal_template(s, outcome)) is None


@pytest.mark.parametrize("nid", [k for k, s in S.items() if s.get("kind") == "normal"])
def test_every_normal_has_signal_checks(nid):
    s = S[nid]
    assert s.get("keep") and len(s["signal_checks"]) == len(s["safe_signals"])


def test_normal_turn_with_home_invite_regenerates():
    bad = json.dumps({"reply": "그럼 우리 집으로 놀러 와. 거기서 이야기하자.",
                      "choices": {"correct": "a.", "doubtful": "b.", "other": "c."}}, ensure_ascii=False)
    p = FakeProvider(bad)
    res = PracticeEngine(p).turn(TurnRequest(scenario_id="normal_cafe_01",
                                             messages=[Message(role="ai", text=CAFE["opening_line"]),
                                                       Message(role="child", text="어디서 만나요?")]))
    assert res.source == "fallback" and "우리 집" not in res.reply


# ---- 백엔드 2차 리뷰: 원본에 같은 단어가 있어도 위험 요구는 막는다 --------------------------------
from app.scenarios import normal_risk_hits  # noqa: E402

SUPPORT = S["normal_game_support_01"]  # 원본: '고객센터는 비밀번호를 절대 묻지 않아요'
MARKET = S["normal_game_market_01"]  # 원본: '게임 안 공식 거래소에 올려 둘게'


def _variant_of(base, opening, child_setup=None):
    v = base_as_variant(base).model_dump()
    v["opening_line"] = opening
    if child_setup:
        v["child_setup"] = child_setup
    from app.schemas import Variant
    return Variant(**v)


@pytest.mark.parametrize("text", [
    "고객센터는 비밀번호를 절대 묻지 않아요.",
    "비밀번호는 누구에게도 알려 주지 마세요.",
    "돈을 먼저 보낼 필요는 없어요.",
    "빨리 정하지 않아도 돼요.",
])
def test_safety_notices_allowed(text):
    assert normal_risk_hits(text) == []


@pytest.mark.parametrize("text", [
    "본인 확인을 위해 비밀번호를 알려 주세요.",
    "고객센터는 비밀번호를 묻지 않지만, 이번에는 비밀번호를 알려 주세요.",
    "비밀번호를 알려 주지 않으면 계정이 정지돼요.",
    "비밀번호 알려 주면 안 돼?",
    "거래소 말고 내 계좌로 먼저 송금해 줘.",
    "아이템은 선입금하면 바로 보내 줄게.",
])
def test_risky_requests_rejected(text):
    assert normal_risk_hits(text)


def test_support_variant_asking_password_rejected():
    # 사례 1: 비밀번호를 묻지 않던 상황에서 비밀번호를 요구
    bad = _variant_of(SUPPORT, "안녕하세요, 게임 고객센터예요. 확인을 위해 비밀번호를 알려 주세요. 문의는 게임 안 메뉴에 남겨 주세요.")
    assert any(p.startswith("risk_phrase") for p in check_variant(SUPPORT, bad))


def test_support_variant_asking_password_falls_back():
    data = {"title": SUPPORT["title"], "child_setup": SUPPORT["child_setup"],
            "ai_role": {"name": SUPPORT["ai_role"]["name"], "persona": SUPPORT["ai_role"]["persona"]},
            "opening_line": "게임 고객센터예요. 계정 확인을 위해 비밀번호를 알려 주세요. 게임 안 메뉴에서 확인할게요."}
    res = Variator(FakeProvider(json.dumps(data, ensure_ascii=False)), S).generate(
        VariantRequest(scenario_id="normal_game_support_01"))
    assert res.source == "fallback" and res.variant.opening_line == SUPPORT["opening_line"]


def test_market_variant_turned_into_transfer_rejected():
    # 사례 2: 공식 거래소 안내가 개인 송금·선입금 요구로 바뀜
    bad = _variant_of(MARKET, "그 아이템 거래소 말고 내 계좌로 먼저 송금해 주면 보내 줄게. 천천히 생각해 봐.")
    assert any(p.startswith("risk_phrase") for p in check_variant(MARKET, bad))
    bad2 = _variant_of(MARKET, "거래소에 올리기 전에 선입금해 주면 너한테만 싸게 줄게. 천천히 생각해 봐.")
    assert any(p.startswith("risk_phrase") for p in check_variant(MARKET, bad2))


@pytest.mark.parametrize("nid,reply", [
    ("normal_game_support_01", "확인해 볼게요. 계정 확인을 위해 비밀번호를 알려 주세요."),
    ("normal_game_market_01", "거래소는 수수료가 있으니 그냥 내 계좌로 송금해 줘."),
    ("normal_cafe_01", "좋아요. 그럼 보증금 먼저 입금해 주면 바로 일할 수 있어요."),
])
def test_normal_turn_with_new_risk_request_falls_back(nid, reply):
    # 사례 3: 정상 상황의 다음 턴에 새로운 위험 요구
    s = S[nid]
    raw = json.dumps({"reply": reply, "choices": {"correct": "a.", "doubtful": "b.", "other": "c."}}, ensure_ascii=False)
    p = FakeProvider(raw)
    res = PracticeEngine(p).turn(TurnRequest(scenario_id=nid, messages=[
        Message(role="ai", text=s["opening_line"]), Message(role="child", text="어떻게 하면 돼요?")]))
    assert res.source == "fallback" and normal_risk_hits(res.reply) == []
    assert p.calls == 2  # 1번 다시 만들어 보고 고정 대사로


def test_normal_turn_safety_notice_kept():
    s = SUPPORT
    raw = json.dumps({"reply": "걱정 마세요. 고객센터는 비밀번호를 절대 묻지 않아요.",
                      "choices": {"correct": "이건 좀 이상해서 안 할래요.", "doubtful": "괜찮은 것 같긴 한데 불안해요.",
                                  "other": "네, 메뉴에 문의를 남길게요."}}, ensure_ascii=False)
    res = PracticeEngine(FakeProvider(raw)).turn(TurnRequest(scenario_id="normal_game_support_01", messages=[
        Message(role="ai", text=s["opening_line"]), Message(role="child", text="비밀번호 알려 줘야 해요?")]))
    assert res.source == "model"


@pytest.mark.parametrize("nid", [k for k, s in S.items() if s.get("kind") == "normal"])
def test_original_normal_texts_have_no_risk_request(nid):
    from app.practice import NORMAL_FALLBACK
    s = S[nid]
    for text in (s["title"], s["child_setup"], s["opening_line"], s["ai_role"]["persona"], NORMAL_FALLBACK):
        assert normal_risk_hits(text) == [], text
