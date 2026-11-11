"""콘텐츠(단서 체계 등) 로더. T-12·T-14 에서 프롬프트에 단서를 넣을 때 쓴다."""
import json
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"


def load_clues() -> dict:
    return json.loads((CONTENT_DIR / "clues.json").read_text(encoding="utf-8"))


def load_scenarios(area_id: str = "scam") -> dict:
    return json.loads((CONTENT_DIR / "scenarios" / f"{area_id}.json").read_text(encoding="utf-8"))


def load_all_scenarios() -> dict[str, dict]:
    """content/scenarios/*.json 의 모든 시나리오를 id 로 찾을 수 있게 모은다."""
    result: dict[str, dict] = {}
    for path in sorted((CONTENT_DIR / "scenarios").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for s in data["scenarios"]:
            result[s["id"]] = {**s, "area": data["area"], "ai_rules": data["ai_rules"]}
    return result


def load_safety_cases() -> dict:
    return json.loads((CONTENT_DIR / "safety_cases.json").read_text(encoding="utf-8"))


def clues_for_area(data: dict, area_id: str) -> list[dict]:
    return [c for c in data["clues"] if area_id in c["areas"]]
