"""T-32 진단 결과 → 시작 난이도, 자주 쓰는 앱 → 연습 플랫폼."""
import json
import random

import pytest

from app.content import load_all_scenarios
from app.providers import FakeProvider
from app.schemas import VariantRequest
from app.setup import platforms_for_apps, start_difficulty
from app.variation import PLATFORM_NAMES, Variator

SCENARIOS = load_all_scenarios()


@pytest.mark.parametrize("risky,level", [(0, 2), (1, 2), (2, 1), (3, 1), (None, 1)])
def test_start_difficulty(risky, level):
    assert start_difficulty(risky) == level


def test_apps_to_platforms_with_aliases_and_unknown():
    platforms, unknown = platforms_for_apps(["카톡", "Instagram", "로블록스", "싸이월드"])
    assert platforms == ["text_message", "open_chat", "sns_dm", "game_chat"]
    assert unknown == ["싸이월드"]


def test_all_mapped_platforms_are_known():
    from app.setup import SETUP
    for app in SETUP["apps"]:
        assert set(app["platforms"]) <= set(PLATFORM_NAMES), app["name"]


def test_setup_http(client):
    status, body = client.request("POST", "/internal/v1/practice/setup",
                                  {"favorite_apps": ["인스타", "게임"], "diagnosis_risky_count": 2})
    assert status == 200
    assert body == {"start_difficulty": 1, "preferred_platforms": ["sns_dm", "game_chat"], "unknown_apps": []}
    assert client.request("POST", "/internal/v1/practice/setup", {"diagnosis_risky_count": 5})[0] == 422


def test_variant_uses_favorite_app_platform():
    p = FakeProvider("x")
    r = Variator(p, SCENARIOS, random.Random(0)).generate(
        VariantRequest(scenario_id="scam_game_item_01", favorite_apps=["디스코드"]))
    assert "오픈채팅" in p.last_prompt  # 디스코드 → open_chat (게임 시나리오에서 가능한 플랫폼)


def test_variant_ignores_app_platform_not_in_scenario():
    p = FakeProvider("x")
    Variator(p, SCENARIOS, random.Random(0)).generate(
        VariantRequest(scenario_id="scam_game_item_01", favorite_apps=["알바몬"]))  # job_board 는 게임 시나리오에 없음
    assert "채용 사이트" not in p.last_prompt.split("[바꿀 말투]")[0]


def test_every_scenario_has_a_difficulty():
    assert {s["difficulty"] for s in SCENARIOS.values() if s["kind"] == "risk"} <= {1, 2}
