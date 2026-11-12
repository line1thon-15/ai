"""T-04 시나리오·정상 상황 형식 검사. 단서 ID 는 content/clues.json 과 맞아야 한다."""
import re

import pytest

from app.content import clues_for_area, load_clues, load_scenarios

CLUES = load_clues()
CLUE_IDS = {c["id"] for c in CLUES["clues"]}
AREAS = [a["id"] for a in CLUES["areas"]]  # scam, identity_lending, friend_pressure (T-29)
FILES = {a: load_scenarios(a) for a in AREAS}
DATA = FILES["scam"]
# 모든 영역의 시나리오 (각 시나리오에 영역 id 를 붙여 둔다)
SCENARIOS = [{**s, "_area": a} for a, d in FILES.items() for s in d["scenarios"]]
SCAM = [s for s in SCENARIOS if s["_area"] == "scam"]


def _texts(s):
    yield s["opening_line"]
    for c in s["clues"]:
        yield c["reveal_line"]
    for n in s["normal_situations"]:
        yield n["opening_line"]


@pytest.mark.parametrize("area", AREAS)
def test_area_and_rules(area):
    assert FILES[area]["area"] == area and FILES[area]["version"] == "v1"
    assert len(FILES[area]["ai_rules"]) >= 5


@pytest.mark.parametrize("area", AREAS)
def test_scenarios_cover_all_area_clues(area):
    """T-29: 영역마다 시나리오 4개 이상, 그 영역의 단서가 모두 한 번 이상 나온다."""
    mine = [s for s in SCENARIOS if s["_area"] == area]
    used = {c["id"] for s in mine for c in s["clues"]}
    assert len(mine) >= 4
    assert used == {c["id"] for c in clues_for_area(CLUES, area)}


@pytest.mark.parametrize("area", AREAS)
def test_each_area_has_non_parttime_scenarios(area):
    """'고수익 알바는 고등학생만' 규칙 때문에, 영역마다 알바가 아닌 시나리오가 2개 이상 있어야 한다."""
    mine = [s for s in SCENARIOS if s["_area"] == area]
    assert len([s for s in mine if "알바" not in s["title"]]) >= 2


def test_parttime_pair_covers_all_scam_clues():
    """시연(사기 연습 2회)에 쓰는 알바 시나리오 두 개만으로 사기 단서 6개가 모두 나온다."""
    pair = [s for s in SCAM if s["id"] in ("scam_dm_parttime_01", "scam_jobboard_link_01")]
    assert {c["id"] for s in pair for c in s["clues"]} == {c["id"] for c in clues_for_area(CLUES, "scam")}


def test_middle_school_scenarios_exist():
    """'고수익 알바는 고등학생만' 규칙 때문에, 알바가 아닌 사기 시나리오가 있어야 한다."""
    ids = {s["id"] for s in SCAM}
    assert {"scam_game_item_01", "scam_allowance_event_01"} <= ids


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s["id"])
def test_opening_line_shows_only_opening_clues(s):
    """첫 대사에는 at_opening 단서의 말만 들어간다 (나머지 단서는 정해진 때에 드러나야 함)."""
    keywords = {c["id"]: c["keywords"] for c in CLUES["clues"]}
    for c in s["clues"]:
        if not c.get("at_opening"):
            hits = [k for k in keywords[c["id"]] if k in s["opening_line"]]
            assert not hits, f"첫 대사에 {c['id']} 의 말 {hits}"


@pytest.mark.parametrize("s", SCENARIOS, ids=lambda s: s["id"])
def test_reveal_line_has_own_keyword(s):
    """단서 대사에 그 단서의 키워드가 있어야 대체 대사로 써도 '드러났다'고 인정된다."""
    keywords = {c["id"]: c["keywords"] for c in CLUES["clues"]}
    for c in s["clues"]:
        assert any(k in c["reveal_line"] for k in keywords[c["id"]]), f"{c['id']}: {c['reveal_line']}"


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
        assert s["_area"] in next(x for x in CLUES["clues"] if x["id"] == c["id"])["areas"]
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


# ---- T-29 검수 반영: 첫 대사는 상황 시작만, 단서는 다음 대사부터 -------------------------
NEW_AREAS = ("identity_lending", "friend_pressure")


@pytest.mark.parametrize("s", [s for s in SCENARIOS if s["_area"] in NEW_AREAS], ids=lambda s: s["id"])
def test_new_area_opening_has_no_clue(s):
    """첫 대사와 단서 1이 겹치지 않게: 첫 대사에는 단서가 없고, 시작 선택지(opening_choices)가 있다."""
    assert not any(c.get("at_opening") for c in s["clues"])
    oc = s["opening_choices"]
    assert set(oc) == {"correct", "doubtful", "other"} and all(v.endswith(".") for v in oc.values())
    first = s["clues"][0]["reveal_line"]
    assert first not in s["opening_line"] and s["opening_line"] not in first
