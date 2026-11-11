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


def test_scenarios_cover_all_scam_clues():
    used = {c["id"] for s in SCENARIOS for c in s["clues"]}
    assert len(SCENARIOS) >= 4
    assert used == {c["id"] for c in clues_for_area(CLUES, "scam")}


def test_parttime_pair_covers_all_scam_clues():
    """시연(사기 연습 2회)에 쓰는 알바 시나리오 두 개만으로 사기 단서 6개가 모두 나온다."""
    pair = [s for s in SCENARIOS if s["id"] in ("scam_dm_parttime_01", "scam_jobboard_link_01")]
    assert {c["id"] for s in pair for c in s["clues"]} == {c["id"] for c in clues_for_area(CLUES, "scam")}


def test_middle_school_scenarios_exist():
    """'고수익 알바는 고등학생만' 규칙 때문에, 알바가 아닌 사기 시나리오가 있어야 한다."""
    ids = {s["id"] for s in SCENARIOS}
    assert {"scam_game_item_01", "scam_allowance_event_01"} <= ids


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s["id"])
def test_reveal_line_does_not_leak_later_clues(s):
    """단서 대사(대체 대사로도 쓰임)에 아직 나오지 않은 뒤 단서의 말이 섞이면 한 턴에 단서가 2개 드러난다."""
    keywords = {c["id"]: c["keywords"] for c in CLUES["clues"]}
    order = [c["id"] for c in s["clues"]]
    for i, c in enumerate(s["clues"]):
        lines = [c["reveal_line"]] + ([s["opening_line"]] if c.get("at_opening") else [])
        for later in order[i + 1:]:
            for line in lines:
                hits = [k for k in keywords[later] if k in line]
                assert not hits, f"{c['id']} 대사에 뒤 단서 {later} 의 말 {hits}: {line}"


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
