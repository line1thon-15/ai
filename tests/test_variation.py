"""T-13 단서 고정 변형: 단서 ID·순서·시점은 그대로, 겉모습만 바뀐다."""
import json
import random
from pathlib import Path

import pytest

from app.content import load_all_scenarios
from app.practice import PracticeEngine
from app.providers import FakeProvider
from app.scenarios import InvalidVariant, base_as_variant, check_variant
from app.schemas import TurnRequest, Variant, VariantRequest
from app.variation import InvalidAxis, Variator, build_prompt

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
SCENARIOS = load_all_scenarios()
SID = "scam_dm_parttime_01"
BASE = SCENARIOS[SID]
SAMPLE = json.loads((CONTRACTS / "practice.variant.response.json").read_text(encoding="utf-8"))
REQ = json.loads((CONTRACTS / "practice.variant.request.json").read_text(encoding="utf-8"))


def model_json(variant: dict, **override) -> str:
    """변형 샘플을 '모델이 돌려줄 JSON' 모양으로 바꾼다."""
    data = {
        "title": variant["title"],
        "child_setup": variant["child_setup"],
        "ai_role": {"name": variant["ai_role"]["name"], "persona": variant["ai_role"]["persona"]},
        "opening_line": variant["opening_line"],
        "clues": [{"id": c["id"], "reveal_line": c["reveal_line"]} for c in variant["clues"]],
    }
    if variant.get("opening_choices"):
        data["opening_choices"] = variant["opening_choices"]
    data.update(override)
    return json.dumps(data, ensure_ascii=False)


def gen(reply, **req):
    return Variator(FakeProvider(reply), SCENARIOS, random.Random(0)).generate(VariantRequest(**{**REQ, **req}))


# ---- 원본 콘텐츠 ------------------------------------------------------------

@pytest.mark.parametrize("sid", [k for k, v in SCENARIOS.items() if v["kind"] == "risk"])
def test_base_scenarios_pass_variant_check(sid):
    assert check_variant(SCENARIOS[sid], base_as_variant(SCENARIOS[sid])) == []


# ---- 생성 -------------------------------------------------------------------

def test_model_variant_matches_contract():
    r = gen(model_json(SAMPLE["variant"]))
    assert r.source == "model" and r.model_dump() == SAMPLE


def test_prompt_contains_axes_and_clues():
    p = build_prompt(BASE, "open_chat", "친구처럼 편한 말투", "물건 포장 알바")
    assert "오픈채팅" in p and "물건 포장 알바" in p
    assert all(f"- {c['id']}:" in p for c in BASE["clues"])


def test_missing_clue_line_falls_back():
    bad = model_json(SAMPLE["variant"], clues=[{"id": "too_good_pay", "reveal_line": "한 달에 300만 원도 벌어."}])
    r = gen(bad)
    assert r.source == "fallback" and r.variant.opening_line == BASE["opening_line"]


def test_clue_line_without_clue_meaning_falls_back():
    v = json.loads(model_json(SAMPLE["variant"]))
    v["clues"][3]["reveal_line"] = "오늘 날씨 좋다."  # keep_secret 이 사라짐
    assert gen(json.dumps(v, ensure_ascii=False)).source == "fallback"


def test_unsafe_variant_falls_back():
    bad = model_json(SAMPLE["variant"], opening_line="여기서 신청해: http://oo-job.kr 하루에 15만 원 벌어")
    assert gen(bad).source == "fallback"


def test_model_cannot_change_clue_timing():
    v = json.loads(model_json(SAMPLE["variant"]))
    v["clues"][0]["at_opening"] = False
    v["clues"][1]["reveal_when"] = "아무 때나"
    r = gen(json.dumps(v, ensure_ascii=False))
    assert r.source == "model"
    assert [c.reveal_when for c in r.variant.clues] == [c["reveal_when"] for c in BASE["clues"]]
    assert r.variant.clues[0].at_opening is True


def test_axes_must_come_from_scenario():
    with pytest.raises(InvalidAxis):
        gen("{}", platform="telegram")


def test_random_axes_avoid_base_platform():
    r = gen("not json", platform=None, tone=None, context=None)
    assert r.source == "fallback"
    provider = FakeProvider(model_json(SAMPLE["variant"]))
    Variator(provider, SCENARIOS, random.Random(1)).generate(VariantRequest(scenario_id=SID))
    assert "SNS 쪽지(DM)" not in provider.last_prompt.split("[바꿀 말투]")[0]


# ---- 변형으로 연습 ------------------------------------------------------------

VARIANT = Variant.model_validate(SAMPLE["variant"])


def test_start_with_variant():
    r = PracticeEngine(FakeProvider()).start(SID, VARIANT)
    assert r.reply == VARIANT.opening_line and r.revealed_clue_ids == ["too_good_pay"]
    assert r.ai_role_name == "오픈채팅 방장 '지니'"


def test_turn_fallback_uses_variant_line():
    class Boom:
        def generate(self, prompt, *, json_mode=False):
            raise RuntimeError

    req = TurnRequest(scenario_id=SID, variant=VARIANT, revealed_clue_ids=["too_good_pay"],
                      messages=[{"role": "ai", "text": VARIANT.opening_line}, {"role": "child", "text": "어떻게 해?"}])
    r = PracticeEngine(Boom()).turn(req)
    assert r.reply == VARIANT.clues[1].reveal_line


def test_tampered_variant_is_rejected():
    tampered = VARIANT.model_copy(update={"clues": VARIANT.clues[:2]})
    with pytest.raises(InvalidVariant):
        PracticeEngine(FakeProvider()).start(SID, tampered)


def test_variant_http(start_server):
    client = start_server(FakeProvider(model_json(SAMPLE["variant"])))
    status, body = client.request("POST", "/internal/v1/practice/variant", REQ)
    assert status == 200 and body == SAMPLE
    status, body = client.request("POST", "/internal/v1/practice/start", {"scenario_id": SID, "variant": body["variant"]})
    assert status == 200 and body["reply"] == SAMPLE["variant"]["opening_line"]
    bad = json.loads(json.dumps(SAMPLE["variant"]))
    bad["clues"] = bad["clues"][:1]
    assert client.request("POST", "/internal/v1/practice/start", {"scenario_id": SID, "variant": bad}) == (
        422, {"error": "invalid_variant"})
    assert client.request("POST", "/internal/v1/practice/variant", {"scenario_id": SID, "platform": "x"}) == (
        422, {"error": "invalid_request", "fields": ["platform"]})
