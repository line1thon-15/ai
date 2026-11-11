"""T-04 시나리오·정상 상황 형식 검사. 단서 ID 는 content/clues.json 과 맞아야 한다."""
import re

import pytest

from app.content import clues_for_area, load_clues, load_scenarios

CLUES = load_clues()
CLUE_IDS = {c["id"] for c in CLUES["clues"]}
DATA = load_scenarios("scam")
SCENARIOS = DATA["scenarios"]


def _texts(s):
    yield s["opening_line"]
    for c in s["clues"]:
        yield c["reveal_line"]
    for n in s["normal_situations"]:
        yield n["opening_line"]


def test_area_and_rules():
    assert DATA["area"] == "scam" and DATA["version"] == "v1"
    assert len(DATA["ai_rules"]) >= 5


def test_two_scenarios_cover_all_scam_clues():
    used = {c["id"] for s in SCENARIOS for c in s["clues"]}
    assert len(SCENARIOS) == 2
    assert used == {c["id"] for c in clues_for_area(CLUES, "scam")}


def test_scenario_ids_unique():
    ids = [s["id"] for s in SCENARIOS] + [n["id"] for s in SCENARIOS for n in s["normal_situations"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s["id"])
def test_scenario_is_complete(s):
    for key in ["title", "platform", "difficulty", "child_setup", "opening_line", "safe_ending"]:
        assert s.get(key), f"{s['id']}: {key} 가 비어 있음"
    assert all(s["ai_role"].get(k) for k in ["name", "persona", "tone"])
    assert len(s["clues"]) >= 3
    for c in s["clues"]:
        assert c["id"] in CLUE_IDS, f"모르는 단서 ID: {c['id']}"
        assert "scam" in next(x for x in CLUES["clues"] if x["id"] == c["id"])["areas"]
        assert c["reveal_when"] and c["reveal_line"]
    ids = [c["id"] for c in s["clues"]]
    assert len(ids) == len(set(ids))
    for key in ["rule", "platform", "tone", "context"]:
        assert s["variation_axes"].get(key)


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s["id"])
def test_normal_situations(s):
    normals = s["normal_situations"]
    assert len(normals) >= 2
    scenario_clue_ids = {c["id"] for c in s["clues"]}
    for n in normals:
        for key in ["title", "platform", "summary", "opening_line"]:
            assert n.get(key), f"{n['id']}: {key} 가 비어 있음"
        assert len(n["safe_signals"]) >= 2
        # 정상 상황은 '시나리오 단서가 빠진 모습'이어야 한다
        assert n["contrast_clues"] and set(n["contrast_clues"]) <= CLUE_IDS
        assert set(n["contrast_clues"]) & scenario_clue_ids


def test_no_real_looking_contacts():
    text = " ".join(t for s in SCENARIOS for t in _texts(s))
    assert not re.search(r"\d{2,3}-\d{3,4}-\d{4}", text)
    assert "http" not in text
    assert all(d.startswith("example.com") for d in re.findall(r"[\w.-]+\.(?:com|kr|net)\S*", text))
