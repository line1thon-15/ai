"""안전 필터를 T-05 세트 전체와 콘텐츠 대사로 확인한다."""
import pytest

from app.content import load_clues, load_safety_cases, load_scenarios
from app.safety import MASK, filter_input, filter_output

CASES = load_safety_cases()["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_safety_case(case):
    if case["stage"] == "input":
        result = filter_input(case["text"])
    else:
        result = filter_output(case["text"], case["speaker"])
    assert result.action == case["expect"], f"{case['id']}: {result}"


def test_mask_replaces_values():
    r = filter_input("제 번호는 010-0000-0000이에요")
    assert r.action == "mask" and "010" not in r.text and MASK in r.text


def _content_lines():
    for c in load_clues()["clues"]:
        yield from c["example_lines"]
    for area in ("scam", "identity_lending", "friend_pressure"):
        for s in load_scenarios(area)["scenarios"]:
            yield s["opening_line"]
            yield from (c["reveal_line"] for c in s["clues"])
            yield from (n["opening_line"] for n in s["normal_situations"])
            yield from (n["fallback_line"] for n in s["normal_situations"] if n.get("fallback_line"))


@pytest.mark.parametrize("line", list(_content_lines()))
def test_content_lines_pass_output_filter(line):
    """연습에 필요한 대사가 필터에 막히면 서비스가 안 된다."""
    assert filter_output(line, "roleplay").action == "allow"
