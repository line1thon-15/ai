"""T-74 힌트 문장. 힌트 단계는 백엔드가 정하고(T-36), AI 는 그 단계에 맞는 문장만 만든다.

단계: 0 없음 / 1 약함(어디를 볼지만) / 2 중간(무엇이 이상한지 묻기) / 3 강함(단서 이름과 안전한 대처)
- 1·2단계 문장은 content/clues.json 의 hints, 3단계는 단서 이름 + safe_action 으로 만든다.
- 힌트는 '이번 응답이 다루는 단서(target_clue_id)'에 맞춘다. 정상 상황은 단서가 없어 정상 상황용 문장을 쓴다.
- 미리 써 둔 문장이라 결과가 늘 같고, 모델을 부르지 않는다.
"""
from .scenarios import CLUE_DEFS

MAX_HINT_LEVEL = 3

NORMAL_HINTS = {
    1: "상대가 무엇을 해 달라고 하는지 차분히 살펴봐요.",
    2: "돈이나 비밀, 모르는 링크를 요구하는지 확인해 봐요.",
    3: "위험 신호가 보이지 않는 상황이에요. 그래도 믿는 어른에게 알려 두면 더 좋아요.",
}
GENERIC_HINTS = {
    1: "상대가 무엇을 해 달라고 하는지 다시 읽어 봐요.",
    2: "돈, 정보, 비밀, 재촉 중에 이상한 말이 있는지 생각해 봐요.",
    3: "이상한 말이 있으면 따르지 말고 믿는 어른에게 먼저 물어봐요.",
}


def hint_text(scenario: dict, target_clue_id: str | None, level: int) -> str | None:
    if not level or level < 1:
        return None
    level = min(level, MAX_HINT_LEVEL)
    if scenario.get("kind") == "normal":
        return NORMAL_HINTS[level]
    clue = CLUE_DEFS.get(target_clue_id) if target_clue_id else None
    if clue is None:
        return GENERIC_HINTS[level]
    if level == 3:
        return f"'{clue['name']}' 신호예요. {clue['safe_action']}."
    return clue["hints"][str(level)]
