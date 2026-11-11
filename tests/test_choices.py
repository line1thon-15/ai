"""선택지 3개 (정답 correct · 의심되는 답 doubtful · 다른 답 other)."""
import json

import pytest

from app.choices import choice_problem, GENERIC, KINDS, MAX_LENGTH_GAP, NORMAL_GENERIC, arrange, template_texts, validate_texts
from app.content import load_clues
from app.practice import PracticeEngine
from app.providers import FakeProvider
from app.schemas import TurnRequest

CLUES = load_clues()["clues"]
SID = "scam_dm_parttime_01"
OPENING = "안녕하세요! 집에서 폰으로 하루 두 시간만 하면 되는 알바예요. 하루에 20만 원 벌 수 있어요. 관심 있으세요?"
GOOD = {"correct": "교육비를 먼저 내라니 이상해요. 안 보낼래요.",
        "doubtful": "돌려준다고 하니까, 일단 보내 볼게요.",
        "other": "네, 교육비는 지금 바로 보낼게요."}


def model(reply="교육비 3만 원만 먼저 보내 주세요.", ids=("advance_payment",), choices=GOOD):
    return json.dumps({"reply": reply, "revealed_clue_ids": list(ids), "choices": choices}, ensure_ascii=False)


def turn(provider, child="와, 좋아요!", revealed=("too_good_pay",)):
    req = TurnRequest.model_validate({
        "scenario_id": SID, "revealed_clue_ids": list(revealed),
        "messages": [{"role": "ai", "text": OPENING},
                     {"role": "child", "text": child, "choice_kind": "other", "clue_id": "too_good_pay"}]})
    return PracticeEngine(provider).turn(req)


def kinds(choices):
    return sorted(c.kind for c in choices)


# ---- 고정 선택지(콘텐츠) ------------------------------------------------------

@pytest.mark.parametrize("clue", CLUES, ids=lambda c: c["id"])
def test_every_clue_template_passes_rules(clue):
    assert validate_texts(clue["choice_templates"]) == clue["choice_templates"]


def test_generic_template_passes_rules():
    assert validate_texts(GENERIC) == GENERIC


def test_arrange_gives_one_of_each_kind():
    cs = arrange(GOOD)
    assert [c.id for c in cs] == ["c1", "c2", "c3"] and kinds(cs) == sorted(KINDS)
    assert arrange(GOOD) == cs  # 같은 입력이면 같은 순서


def test_correct_answer_is_not_always_in_the_same_place():
    positions = {[c.kind for c in arrange(c["choice_templates"])].index("correct") for c in CLUES}
    assert len(positions) >= 2


# ---- 첫 대사 / 다음 턴 ---------------------------------------------------------

def test_start_has_three_choices_for_opening_clue():
    r = PracticeEngine(FakeProvider()).start(SID)
    assert r.target_clue_id == "too_good_pay" and kinds(r.choices) == sorted(KINDS)
    assert {c.text for c in r.choices} == set(template_texts("too_good_pay").values())


def test_model_choices_are_used():
    r = turn(FakeProvider(model()))
    assert r.choices_source == "model" and r.target_clue_id == "advance_payment"
    assert {c.kind: c.text for c in r.choices} == GOOD


@pytest.mark.parametrize("bad", [
    {**GOOD, "correct": "음… 잘 모르겠어요."},                       # 정답인데 조심하는 말이 없음
    {**GOOD, "other": "싫어요, 안 보낼래요."},                       # 다른 답인데 거절함
    {**GOOD, "doubtful": GOOD["other"]},                            # 같은 문장
    {**GOOD, "other": "여기로 보낼게요 http://oo-pay.kr"},           # 진짜 같은 링크
    {**GOOD, "other": "제 번호는 010-1234-5678이에요."},             # 개인정보
    {**GOOD, "other": "네" * 61},                                    # 너무 김
    {"correct": GOOD["correct"], "other": GOOD["other"]},           # 하나 빠짐
    "선택지 없음",
])
def test_bad_model_choices_fall_back_to_template_but_keep_reply(bad):
    r = turn(FakeProvider(model(choices=bad)))
    assert r.source == "model" and r.choices_source == "template"
    assert {c.text for c in r.choices} == set(template_texts("advance_payment").values())


def test_no_new_clue_targets_latest_revealed():
    r = turn(FakeProvider(model(reply="정말 쉬운 일이에요.", ids=(), choices=None)), revealed=("too_good_pay", "urgency"))
    assert r.target_clue_id == "urgency" and r.choices_source == "template"


# 실제 Gemini 출력 (2026-11-11 로컬 확인): 5문장이라 예전에는 통째로 버려졌다
REAL_LONG = "와, 빠르시네요! 좋아요! 이 알바는 오늘 딱 한 명만 더 뽑는 거라 지금 바로 결정하셔야 해요. 다른 분들이 너무 많아서요. 괜찮으세요?"


def test_long_reply_is_shortened_keeping_clue_sentence():
    p = FakeProvider(model(reply=REAL_LONG, ids=("urgency",),
                           choices={"correct": "이렇게 재촉하니 이상해요. 안 할래요.", "doubtful": "오늘까지라니 급하지만, 그냥 할게요.",
                                    "other": "네, 지금 바로 할게요."}))
    r = turn(p)
    assert p.calls == 1 and r.source == "model"
    assert r.reply == "와, 빠르시네요! 이 알바는 오늘 딱 한 명만 더 뽑는 거라 지금 바로 결정하셔야 해요."
    assert r.target_clue_id == "urgency" and r.choices_source == "model"


def test_claimed_clue_without_its_words_is_not_counted():
    r = turn(FakeProvider(model(reply="정말 쉬운 일이에요.", ids=("advance_payment",))))
    assert r.revealed_clue_ids == ["too_good_pay"] and r.target_clue_id == "too_good_pay"


def test_fallback_uses_template_for_fallback_clue():
    class Boom:
        def generate(self, prompt, *, json_mode=False):
            raise RuntimeError

    r = turn(Boom())
    assert r.source == "fallback" and r.target_clue_id == "advance_payment" and r.choices_source == "template"


def test_safe_reply_has_no_choices():
    r = turn(FakeProvider(model()), child="나 그냥 죽고 싶어")
    assert r.status == "safe_reply" and r.choices == [] and r.choices_source == "none"


def test_prompt_asks_for_three_kinds():
    p = FakeProvider(model())
    turn(p)
    assert all(f"- {k}:" in p.last_prompt for k in KINDS) and '"choices"' in p.last_prompt


# ---- 길이 균형 (정답이 늘 가장 길면 길이만 보고 고를 수 있다) ------------------------

ALL_TEMPLATES = [c["choice_templates"] for c in CLUES] + [GENERIC, NORMAL_GENERIC]


@pytest.mark.parametrize("texts", ALL_TEMPLATES)
def test_template_lengths_are_close(texts):
    lengths = [len(v) for v in texts.values()]
    assert max(lengths) - min(lengths) <= 5, texts


def test_correct_is_rarely_the_longest():
    longest_correct = sum(1 for t in ALL_TEMPLATES if len(t["correct"]) > max(len(t["doubtful"]), len(t["other"])))
    assert longest_correct <= len(ALL_TEMPLATES) // 4


def test_model_choices_with_big_length_gap_fall_back():
    gap = {**GOOD, "other": "네!"}
    assert len(GOOD["correct"]) - len("네!") > MAX_LENGTH_GAP
    assert validate_texts(gap) is None


def test_hedging_correct_answer_is_not_accepted():
    """'생각해 볼게요'는 여지를 두는 말이라 정답(correct)으로 인정하지 않는다."""
    hedge = {**GOOD, "correct": "지금은 못 정해요. 생각해 볼게요."}
    assert validate_texts(hedge) is None


@pytest.mark.parametrize("clue", CLUES, ids=lambda c: c["id"])
def test_doubtful_template_names_the_problem_then_goes_along(clue):
    """의심되는 답: 무엇이 이상한지 말한 뒤(…) 결국 따른다."""
    d = clue["choice_templates"]["doubtful"]
    assert "," in d and d.endswith(".")



# 실제 Gemini 출력 (2026-11-12 로컬 확인)
@pytest.mark.parametrize("correct", [
    "오늘 바로 결정하라는 건 이상해요. 다시 생각해 볼게요.",   # 여지를 둠
    "오늘 마감이라니 정말 이상해요.",                        # 이상하다고만 함 (의심되는 답과 구분 안 됨)
])
def test_correct_needs_clear_refusal_or_adult(correct):
    assert validate_texts({**GOOD, "correct": correct}) is None


@pytest.mark.parametrize("correct", [
    "게임 밖에서 돈을 먼저 보내는 건 이상해요. 싫어요.",
    "먼저 돈을 내라는 건 이상해요. 안 할래요.",
    "이건 이상해요. 먼저 어른에게 물어볼게요.",
])
def test_clear_correct_answers_pass(correct):
    assert validate_texts({**GOOD, "correct": correct}) is not None



# 실제 Gemini 출력 (2026-11-12 로컬 확인): '네! 알겠어요.'가 문장으로 세어져 3문장 탈락하던 것
@pytest.mark.parametrize("texts", [
    {"correct": "교육비를 먼저 내라고 하니 이상해요. 이 알바는 안 할래요.",
     "doubtful": "교육비를 먼저 내는 게 좀 이상한데… 그래도 보내 볼까요?",
     "other": "네! 알겠어요. 지금 바로 교육비 3만 원 보내 드릴게요!"},
    {"correct": "오늘 바로 정하라고 하니 이상해요. 이 알바는 안 할래요.",
     "doubtful": "오늘까지라니 좀 급하긴 한데, 그래도 바로 할까요?",
     "other": "네! 지금 바로 할게요. 그럼 그렇게 할게요."},
])
def test_short_interjections_do_not_count_as_sentences(texts):
    assert choice_problem(texts) is None


def test_three_real_sentences_still_fail():
    texts = {**GOOD, "other": "좋아요 정말로. 지금 보낼게요 바로. 어디로든 보내 드려요."}
    assert "3문장" in choice_problem(texts)



# ---- 형식 통일: 부호만 보고 정답을 고를 수 없게 --------------------------------------

def test_model_choice_punctuation_is_normalized():
    # 실제 Gemini 출력 (2026-11-12 로컬 확인)
    texts = {"correct": "교육비를 먼저 내라는 건 이상해요. 이 알바는 안 할래요.",
             "doubtful": "교육비를 미리 내야 한다니 좀 이상하긴 하네요… 그래도 보낼까요?",
             "other": "네, 알겠어요! 그럼 교육비 3만원 바로 보내드릴게요."}
    out = validate_texts(texts)
    assert out["doubtful"] == "교육비를 미리 내야 한다니 좀 이상하긴 하네요, 그래도 보낼게요."
    assert out["other"] == "네, 알겠어요. 그럼 교육비 3만원 바로 보내드릴게요."


def test_question_that_cannot_become_statement_falls_back():
    assert "평서문" in choice_problem({**GOOD, "other": "네, 어떻게 하면 되나요?"})


@pytest.mark.parametrize("texts", ALL_TEMPLATES)
def test_templates_share_the_same_format(texts):
    for v in texts.values():
        assert v.endswith(".") and not any(ch in v for ch in "!?…"), v



@pytest.mark.parametrize("raw,expected", [
    ("지금 정하라고 하시니… 바로 해야 할까요?", "지금 정하라고 하시니, 바로 해야겠어요."),
    ("네! 지금 바로 시작할 수 있어요.", "네, 지금 바로 시작할 수 있어요."),
    ("네! 교육비 3만 원을 지금 바로 보내 드릴게요.", "네, 교육비 3만 원을 지금 바로 보내 드릴게요."),
    ("좀 이상하긴 한데, 해볼까요?", "좀 이상하긴 한데, 해볼게요."),
])
def test_normalize_choice_reads_naturally(raw, expected):
    from app.choices import normalize_choice
    assert normalize_choice(raw) == expected
