"""콘텐츠(단서 체계 등) 로더. T-12·T-14 에서 프롬프트에 단서를 넣을 때 쓴다."""
import json
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"


def load_clues() -> dict:
    return json.loads((CONTENT_DIR / "clues.json").read_text(encoding="utf-8"))


def load_scenarios(area_id: str = "scam") -> dict:
    return json.loads((CONTENT_DIR / "scenarios" / f"{area_id}.json").read_text(encoding="utf-8"))


def load_all_scenarios() -> dict[str, dict]:
    """content/scenarios/*.json 의 모든 시나리오를 id 로 찾을 수 있게 모은다.

    kind = "risk"  : 위험 상황 (단서가 있음)
    kind = "normal": 정상 상황 (단서 없음). 위험 시나리오 안의 normal_situations 를 따로 꺼내 등록한다.
    """
    result: dict[str, dict] = {}
    for path in sorted((CONTENT_DIR / "scenarios").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        common = {"area": data["area"], "ai_rules": data["ai_rules"]}
        for s in data["scenarios"]:
            result[s["id"]] = {**s, **common, "kind": "risk"}
            for n in s.get("normal_situations", []):
                result[n["id"]] = {**n, **common, "kind": "normal", "base_scenario_id": s["id"],
                                   "child_setup": n["summary"], "clues": [],
                                   "variation_axes": s["variation_axes"]}  # T-34: 부모 시나리오의 변형 축
    return result


def load_safety_cases() -> dict:
    return json.loads((CONTENT_DIR / "safety_cases.json").read_text(encoding="utf-8"))


def clues_for_area(data: dict, area_id: str) -> list[dict]:
    return [c for c in data["clues"] if area_id in c["areas"]]
