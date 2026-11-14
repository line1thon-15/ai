from app.providers import FakeProvider
from app.schemas import SummaryRequest
from app.summary import build_prompt, clean_summary, generate_summary

REQ = SummaryRequest(
    area="친구의 무리한 부탁",
    practice_count=3,
    found_clues=["압박하는 말투"],
    missed_clues=["돈 요구"],
    growth_level="익숙해지는 중",
)


def test_prompt_contains_backend_values_only():
    p = build_prompt(REQ)
    assert "친구의 무리한 부탁" in p and "압박하는 말투" in p and "돈 요구" in p
    assert "연습 횟수: 3" in p


def test_normal_flow_returns_summary():
    out = generate_summary(REQ, FakeProvider("부탁이 무리한지 생각해 보는 모습이 좋아요. 거절하는 연습을 해 보면 좋겠어요."))
    assert out == "부탁이 무리한지 생각해 보는 모습이 좋아요. 거절하는 연습을 해 보면 좋겠어요."


def test_more_than_two_sentences_is_trimmed():
    raw = "좋아요. 잘했어요. 계속해요. 또 해요."
    assert len(clean_summary(raw, REQ).split(". ")) <= 2


def test_provider_failure_returns_none():
    class Boom:
        def generate(self, prompt):
            raise RuntimeError("timeout")

    assert generate_summary(REQ, Boom()) is None


def test_empty_output_returns_none():
    assert generate_summary(REQ, FakeProvider("   ")) is None


def test_invented_number_is_rejected():
    assert clean_summary("이번 주 연습을 7번 했어요.", REQ) is None


def test_number_from_input_is_allowed():
    assert clean_summary("이번에 3번 연습했어요.", REQ) == "이번에 3번 연습했어요."


def test_too_long_output_is_rejected():
    assert clean_summary("가" * 300, REQ) is None


def test_quotes_are_stripped():
    assert clean_summary('"잘하고 있어요."', REQ) == "잘하고 있어요."
