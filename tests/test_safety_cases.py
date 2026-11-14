"""T-05 안전 필터 테스트 세트 형식 검사. (필터 자체는 T-12, 전체 실행은 T-51)"""
import re
from collections import Counter

import pytest

from app.content import load_clues, load_safety_cases

DATA = load_safety_cases()
CASES = DATA["cases"]
EXPECTS = set(DATA["expect_meanings"])
SPEAKERS = {"input": {"child"}, "output": {"roleplay", "feedback"}}


def test_ids_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_case_is_complete(case):
    for key in ["stage", "speaker", "category", "text", "expect", "reason"]:
        assert case.get(key), f"{case['id']}: {key} 가 비어 있음"
    assert case["expect"] in EXPECTS
    assert case["speaker"] in SPEAKERS[case["stage"]]
    if case["stage"] == "output":
        assert case["expect"] in {"allow", "block"}, "출력은 통과/차단만"


def test_each_stage_has_allow_and_non_allow():
    for stage in ("input", "output"):
        kinds = Counter(c["expect"] == "allow" for c in CASES if c["stage"] == stage)
        assert kinds[True] >= 3 and kinds[False] >= 5, f"{stage}: 통과/차단 사례가 부족"


def test_input_pii_uses_fake_values_only():
    for c in CASES:
        if c["stage"] == "input":
            for digits in re.findall(r"\d{3,}", c["text"]):
                if digits == "010":  # 휴대전화 앞자리는 가짜 값이 아니어도 된다
                    continue
                assert set(digits) == {"0"}, f"{c['id']}: 진짜 같은 숫자 금지"


def test_clue_example_lines_are_not_in_block_cases():
    """연습에 필요한 단서 대사가 차단 사례에 들어가면 안 된다."""
    lines = {l for c in load_clues()["clues"] for l in c["example_lines"]}
    blocked = {c["text"] for c in CASES if c["expect"] == "block"}
    assert not (lines & blocked)
