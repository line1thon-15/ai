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
from app.schemas import FeedbackRequest, JudgeRequest, Message, TurnRequest, VariantRequest
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


@pytest.mark.parametrize("nid", [k for k, s in S.items() if s.get("kind") == "normal"])
def test_normal_fallback_line_fits_situation(nid):
    """T-29: 모델이 실패하면 정상 상황마다 정한 고정 대사를 쓴다 (친구 사이는 반말 등)."""
    s = S[nid]
    p = FakeProvider("not json")
    res = PracticeEngine(p).turn(TurnRequest(scenario_id=nid, messages=[
        Message(role="ai", text=s["opening_line"]), Message(role="child", text="음, 잘 모르겠어요.")]))
    assert res.source == "fallback" and res.reply == (s.get("fallback_line") or res.reply)
    assert normal_risk_hits(res.reply) == []


# ---- T-29 백엔드 리뷰: 첫 대사에서 첫 단서 공개, 단서 없는 응답 처리, 전체 흐름 ----------------------
RISK_IDS = [k for k, s in S.items() if s.get("kind") == "risk"]


@pytest.mark.parametrize("sid", RISK_IDS)
def test_start_reveals_first_clue(sid):
    s = S[sid]
    r = PracticeEngine(FakeProvider("x")).start(sid)
    first = s["clues"][0]["id"]
    assert r.revealed_clue_ids == [first] and r.target_clue_id == first
    if s.get("opening_choices"):
        assert {c.kind: c.text for c in r.choices} == s["opening_choices"]


@pytest.mark.parametrize("sid", RISK_IDS)
def test_turn_without_any_clue_regenerates(sid):
    """드러난 단서가 하나도 없을 때 모델이 단서를 빠뜨리면 다시 생성하고, 그래도 없으면 준비된 단서 대사."""
    s = S[sid]
    no_clue = json.dumps({"reply": "그렇구나. 더 궁금한 거 있어?", "revealed_clue_ids": [],
                          "choices": {"correct": "이상해서 안 할래.", "doubtful": "좀 이상한데 해 볼게.",
                                      "other": "좋아, 할게."}}, ensure_ascii=False)
    p = FakeProvider(no_clue)
    t = PracticeEngine(p).turn(TurnRequest(scenario_id=sid, revealed_clue_ids=[], messages=[
        Message(role="ai", text="안녕"), Message(role="child", text="응?")]))
    assert p.calls == 2 and t.source == "fallback" and len(t.revealed_clue_ids) == 1


def _child(choice, target):
    return Message(role="child", text=choice.text, choice_kind=choice.kind, clue_id=target)


@pytest.mark.parametrize("sid", RISK_IDS)
def test_flow_start_correct_judge_feedback(sid):
    """start → 첫 선택(correct) → judge → feedback: 백엔드는 correct 에서 연습을 끝내므로, 첫 단서는 '찾음'."""
    s = S[sid]
    eng, judge = PracticeEngine(FakeProvider("x")), Judge(FakeProvider("x"), S)
    st = eng.start(sid)
    pick = next(c for c in st.choices if c.kind == "correct")
    msgs = [Message(role="ai", text=st.reply), _child(pick, st.target_clue_id)]
    j = judge.judge(JudgeRequest(scenario_id=sid, messages=msgs, revealed_clue_ids=st.revealed_clue_ids))
    first = s["clues"][0]["id"]
    assert j.source == "choices"
    assert {r.clue_id: r.result for r in j.results}[first] == "found"
    assert all(r.result == "not_shown" for r in j.results if r.clue_id != first)
    fb = judge.feedback(FeedbackRequest(scenario_id=sid, results=j.results))
    assert [c.clue_id for c in fb.cards] == [first] and fb.cards[0].result == "found"


@pytest.mark.parametrize("sid", RISK_IDS)
def test_flow_start_other_turn_judge_feedback(sid):
    """start → 첫 선택(other) → turn(다음 단서) → judge → feedback."""
    s = S[sid]
    eng, judge = PracticeEngine(FakeProvider("x")), Judge(FakeProvider("x"), S)
    st = eng.start(sid)
    pick = next(c for c in st.choices if c.kind == "other")
    msgs = [Message(role="ai", text=st.reply), _child(pick, st.target_clue_id)]
    tr = eng.turn(TurnRequest(scenario_id=sid, messages=msgs, revealed_clue_ids=st.revealed_clue_ids))
    assert tr.status == "ok" and len(tr.revealed_clue_ids) == 2 and len(tr.choices) == 3
    msgs.append(Message(role="ai", text=tr.reply))
    j = judge.judge(JudgeRequest(scenario_id=sid, messages=msgs, revealed_clue_ids=tr.revealed_clue_ids))
    res = {r.clue_id: r.result for r in j.results}
    assert res[s["clues"][0]["id"]] == "missed"
    assert sum(v != "not_shown" for v in res.values()) == 2
    fb = judge.feedback(FeedbackRequest(scenario_id=sid, results=j.results))
    assert len(fb.cards) == 2


# ---- T-29 검수 v2: 아이의 말에 맞는 단서로 이어 가기 (모델이 실패했을 때도) --------------------
@pytest.mark.parametrize("child,expected", [
    ("부모님께 먼저 물어볼게요.", "keep_secret"),
    ("그거 위험한 거 아니에요?", "no_risk_claim"),
    ("좀 생각해 볼게요.", "urgency"),
    ("음.", "lend_identity"),  # 맞는 단서가 없으면 시나리오 순서대로
])
def test_fallback_follows_child_reaction(child, expected):
    sid = "identity_dm_account_01" if expected == "urgency" else "identity_phone_senior_01"
    s = S[sid]
    t = PracticeEngine(FakeProvider("not json")).turn(TurnRequest(scenario_id=sid, messages=[
        Message(role="ai", text=s["opening_line"]), Message(role="child", text=child)]))
    first = s["clues"][0]["id"]
    assert t.source == "fallback" and t.revealed_clue_ids == [expected if child != "음." else first]


def test_every_clue_has_triggers():
    from app.content import load_clues
    for c in load_clues()["clues"]:
        assert c.get("triggers"), c["id"]


# ---- 백엔드 3차 리뷰: 뒤에 붙은 '마세요' 같은 다른 부정 때문에 요구가 통과하면 안 된다 ----------------
BYPASS = [
    "비밀번호를 알려 주세요, 잊지 마세요.",
    "계좌번호를 보내 주세요, 내용을 잊지 마세요.",
    "비밀번호를 알려 주세요. 걱정하지 마세요.",
    "비밀번호 알려 주고 다른 사람한테는 말하지 마세요.",
    "계좌로 송금해 주세요, 늦지 않게요.",
    "고객센터는 비밀번호를 묻지 않지만, 확인을 위해 비밀번호를 입력해 주세요, 걱정 마세요.",
]
STILL_SAFE = [
    "고객센터는 비밀번호를 절대 묻지 않아요.",
    "비밀번호는 누구에게도 알려 주지 마세요.",
    "비밀번호를 알려 달라는 사람은 없어요.",
    "링크는 누르지 마세요.",
    "앱을 설치하지 마세요.",
    "계좌번호는 보내지 않아도 돼요.",
    "돈을 먼저 보낼 필요는 없어요.",
    "빨리 정하지 않아도 돼요.",
]


@pytest.mark.parametrize("text", BYPASS)
def test_trailing_negation_does_not_hide_request(text):
    assert normal_risk_hits(text), text


@pytest.mark.parametrize("text", STILL_SAFE)
def test_safety_notices_still_pass(text):
    assert normal_risk_hits(text) == [], text


@pytest.mark.parametrize("text", BYPASS[:2])
def test_bypass_blocked_in_variant(text):
    bad = _variant_of(SUPPORT, "안녕하세요, 게임 고객센터예요. " + text + " 문의는 게임 안 메뉴에 남겨 주세요.")
    assert any(p.startswith("risk_phrase") for p in check_variant(SUPPORT, bad))


@pytest.mark.parametrize("text", BYPASS[:2])
def test_bypass_blocked_in_turn(text):
    s = SUPPORT
    raw = json.dumps({"reply": text, "choices": {"correct": "a.", "doubtful": "b.", "other": "c."}}, ensure_ascii=False)
    p = FakeProvider(raw)
    res = PracticeEngine(p).turn(TurnRequest(scenario_id="normal_game_support_01", messages=[
        Message(role="ai", text=s["opening_line"]), Message(role="child", text="어떻게 하면 돼요?")]))
    assert res.source == "fallback" and normal_risk_hits(res.reply) == [] and p.calls == 2


@pytest.mark.parametrize("text", BYPASS[:2])
def test_bypass_blocked_in_normal_feedback(text):
    p = FakeProvider(json.dumps({"feedback": text}, ensure_ascii=False))
    res = Judge(p, S).feedback(FeedbackRequest(scenario_id="normal_game_support_01", normal_outcome="over_warned"))
    assert res.source == "fallback"


# ---- PR #2 추가 리뷰 1: 변형하면 시작 선택지도 바뀐 상황에 맞아야 한다 ---------------------------
from app.schemas import OpeningChoices, Variant  # noqa: E402
from app.scenarios import opening_choices_problems, resolve  # noqa: E402

HW = S["friend_homework_01"]  # 원본: 수학 숙제 대신 해 주기
GAME = {"title": "게임 레벨을 대신 올려 달라는 친구",
        "child_setup": "같은 반 친구가 메신저로 게임 레벨을 대신 올려 달라고 해요.",
        "opening_line": "야, 너 게임 잘하잖아. 내 캐릭터 레벨 좀 대신 올려 줘.",
        "ai_role": {"name": "같은 반 친구 '태오'", "persona": "친한 척 조르는 같은 반 친구."}}
GOOD_OC = {"correct": "레벨을 대신 올려 주는 건 안 돼. 네가 해.", "doubtful": "좀 귀찮긴 한데, 이번만 올려 줄게.",
           "other": "응, 그 정도는 내가 올려 줄게."}


def _game_variant(oc=None):
    v = base_as_variant(HW).model_dump()
    v.update(title=GAME["title"], child_setup=GAME["child_setup"], opening_line=GAME["opening_line"],
             context="게임 레벨 대신 올려 주기", opening_choices=oc)
    v["ai_role"].update(GAME["ai_role"])
    return Variant(**v)


def test_variant_with_original_choices_is_rejected():
    """원본(숙제) 선택지를 그대로 단 변형은 상황과 안 맞는다."""
    v = _game_variant(HW["opening_choices"])
    assert any(p.startswith("opening_choices:mismatch") for p in check_variant(HW, v))
    with pytest.raises(Exception):
        PracticeEngine(FakeProvider("x")).start("friend_homework_01", v)


def test_variant_without_choices_does_not_reuse_original():
    v = _game_variant(None)
    assert check_variant(HW, v) == [] and resolve(S, "friend_homework_01", v)["opening_choices"] is None
    r = PracticeEngine(FakeProvider("x")).start("friend_homework_01", v)
    assert all("숙제" not in c.text for c in r.choices) and r.target_clue_id == "burdensome_request"


def test_model_choices_for_new_situation_are_used():
    raw = json.dumps({**GAME, "clues": [{"id": c["id"], "reveal_line": c["reveal_line"]} for c in HW["clues"]],
                      "opening_choices": GOOD_OC}, ensure_ascii=False)
    res = Variator(FakeProvider(raw), S).generate(VariantRequest(scenario_id="friend_homework_01",
                                                                 context="게임 레벨 대신 올려 주기"))
    assert res.source == "model" and res.variant.opening_choices.model_dump() == GOOD_OC
    r = PracticeEngine(FakeProvider("x")).start("friend_homework_01", res.variant)
    assert {c.kind: c.text for c in r.choices} == GOOD_OC


def test_model_stale_choices_are_dropped_not_the_variant():
    raw = json.dumps({**GAME, "clues": [{"id": c["id"], "reveal_line": c["reveal_line"]} for c in HW["clues"]],
                      "opening_choices": HW["opening_choices"]}, ensure_ascii=False)
    res = Variator(FakeProvider(raw), S).generate(VariantRequest(scenario_id="friend_homework_01",
                                                                 context="게임 레벨 대신 올려 주기"))
    assert res.source == "model" and res.variant.opening_choices is None
    r = PracticeEngine(FakeProvider("x")).start("friend_homework_01", res.variant)
    assert all("숙제" not in c.text for c in r.choices)


def test_original_choices_match_original_situation():
    for sid, s in S.items():
        if s.get("opening_choices"):
            assert opening_choices_problems(s, base_as_variant(s)) == [], sid


# ---- PR #2 추가 리뷰 2: 단서 없이 대화가 반복되지 않게 ---------------------------------------------
NO_CLUE = json.dumps({"reply": "그건 나중에 알려 줄게.", "revealed_clue_ids": [],
                      "choices": {"correct": "이상해서 안 할래.", "doubtful": "좀 이상한데 해 볼게.", "other": "좋아, 할게."}},
                     ensure_ascii=False)


def _turn(sid, messages, revealed, raw=NO_CLUE):
    p = FakeProvider(raw)
    return p, PracticeEngine(p).turn(TurnRequest(scenario_id=sid, messages=messages, revealed_clue_ids=revealed))


def test_one_clueless_turn_is_allowed():
    """아이의 질문에 답하는 턴처럼, 단서 없는 턴은 한 번은 허용한다."""
    s = HW
    p, t = _turn("friend_homework_01", [Message(role="ai", text=s["opening_line"]),
                                        Message(role="child", text="왜?")], ["burdensome_request"])
    assert t.source == "model" and t.revealed_clue_ids == ["burdensome_request"] and p.calls == 1


def test_second_clueless_turn_in_a_row_forces_next_clue():
    s = HW
    msgs = [Message(role="ai", text=s["opening_line"]), Message(role="child", text="왜?"),
            Message(role="ai", text="그건 나중에 알려 줄게."), Message(role="child", text="그래서 뭐?")]
    p, t = _turn("friend_homework_01", msgs, ["burdensome_request"])
    assert p.calls == 2 and t.source == "fallback"
    assert t.revealed_clue_ids == ["burdensome_request", s["clues"][1]["id"]]


def test_clueless_turn_allowed_again_after_a_reveal():
    s = HW
    msgs = [Message(role="ai", text=s["opening_line"]), Message(role="child", text="왜?"),
            Message(role="ai", text="그건 나중에 알려 줄게."), Message(role="child", text="그래서 뭐?"),
            Message(role="ai", text=s["clues"][1]["reveal_line"]), Message(role="child", text="싫어.")]
    p, t = _turn("friend_homework_01", msgs, ["burdensome_request", s["clues"][1]["id"]])
    assert t.source == "model" and p.calls == 1


def test_no_forcing_when_all_clues_revealed():
    s = HW
    ids = [c["id"] for c in s["clues"]]
    msgs = [Message(role="ai", text=s["opening_line"]), Message(role="child", text="싫어.")]
    p, t = _turn("friend_homework_01", msgs, ids)
    assert t.source == "model" and p.calls == 1
