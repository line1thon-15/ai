"""단서 체계(content/clues.json) 형식 검사. 내용을 고칠 때 실수를 바로 잡아 준다."""
import re

import pytest

from app.content import clues_for_area, load_clues

DATA = load_clues()
AREA_IDS = {a["id"] for a in DATA["areas"]}
REQUIRED = ["id", "areas", "name", "description", "found_when", "safe_action", "example_lines"]


def test_version_and_areas():
    assert DATA["version"] == "v1"
    assert AREA_IDS == {"scam", "identity_lending", "friend_pressure"}


def test_ids_are_unique_snake_case():
    ids = [c["id"] for c in DATA["clues"]]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", i) for i in ids)


@pytest.mark.parametrize("clue", DATA["clues"], ids=lambda c: c["id"])
def test_clue_is_complete(clue):
    for key in REQUIRED:
        assert clue.get(key), f"{clue['id']}: {key} 가 비어 있음"
    assert set(clue["areas"]) <= AREA_IDS
    assert len(clue["name"]) <= 30, "이름은 한 문장으로 짧게"
    assert len(clue["example_lines"]) >= 2


@pytest.mark.parametrize("clue", DATA["clues"], ids=lambda c: c["id"])
def test_example_lines_contain_clue_keyword(clue):
    """T-13 변형 검사가 쓰는 키워드: 예시 대사에도 들어 있어야 기준이 맞다."""
    assert clue.get("keywords")
    for line in clue["example_lines"]:
        assert any(k in line for k in clue["keywords"]), f"{clue['id']}: {line}"


def test_every_area_has_enough_clues():
    for area in AREA_IDS:
        assert len(clues_for_area(DATA, area)) >= 4, area


def test_example_lines_have_no_real_looking_contacts():
    text = " ".join(l for c in DATA["clues"] for l in c["example_lines"])
    assert not re.search(r"\d{2,3}-\d{3,4}-\d{4}", text), "전화번호 모양은 쓰지 않기"
    assert "http" not in text, "실제 링크 대신 example.com 만 사용"
