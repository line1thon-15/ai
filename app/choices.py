"""아이가 고르는 선택지 3개: 정답(correct) · 의심되는 답(doubtful) · 다른 답(other).

- correct : 위험 신호를 알아채고 안전하게 대처하는 답 (거절하거나 믿는 어른에게 확인)
- doubtful: 이상하다고 느끼지만 끝까지 대처하지 못하는 답 (망설이다가 따르려고 함)
- other   : 상대의 말을 그대로 따르는 답

선택지는 '이번 대사가 다루는 단서(target_clue_id)'에 대한 답이다.
모델이 만든 선택지가 규칙에 안 맞으면 clues.json 의 choice_templates 로 바꾼다.
순서는 글 내용으로 정해지는 해시 순서라, 정답 위치가 늘 같지 않으면서도 같은 입력에는 같은 결과가 나온다.
"""
import hashlib

from .jsonutil import clean_text, count_sentences
from .safety import check_input, check_output
from .scenarios import CLUE_DEFS
from .schemas import Choice

KINDS = ("correct", "doubtful", "other")
MAX_CHOICE_CHARS = 60

# '조심하는 말' (정답 선택지 검사, 규칙 기반 판별에 함께 쓴다)
SAFE_MARKERS = (
    "안 보낼", "안 보내", "안 할", "안 해", "싫", "거절", "이상해", "이상하", "수상", "사기", "의심",
    "안 누를", "안 눌", "안 줄", "안 줘", "못 줘", "생각해 볼", "생각해볼", "확인", "신고", "안 갈",
    "수 없", "안 될", "안 돼", "못 해", "생각해 보", "시간이 필요",
)
ADULT_WORDS = ("부모님", "엄마", "아빠", "선생님", "어른", "보호자")
# '다른 답'에 들어가면 안 되는 분명한 거절 표현
_REFUSAL = ("싫", "거절", "사기", "신고", "안 보낼", "안 할래", "안 누를", "안 줄", "물어볼", "수 없")

GENERIC = {
    "correct": "이건 이상해요. 먼저 어른에게 물어볼게요.",
    "doubtful": "조금 이상하긴 한데… 그래도 한 번 해 볼까요?",
    "other": "좋아요! 어떻게 하면 돼요?",
}


def template_texts(clue_id: str | None) -> dict:
    if clue_id and clue_id in CLUE_DEFS and CLUE_DEFS[clue_id].get("choice_templates"):
        return dict(CLUE_DEFS[clue_id]["choice_templates"])
    return dict(GENERIC)


def _ok_text(text: str) -> bool:
    return (0 < len(text) <= MAX_CHOICE_CHARS and count_sentences(text) <= 2
            and check_input(text).action == "allow" and check_output(text, "roleplay").allowed)


def validate_texts(data) -> dict | None:
    """모델이 준 {"correct": .., "doubtful": .., "other": ..} 가 규칙에 맞으면 정리해서 돌려준다."""
    if not isinstance(data, dict):
        return None
    try:
        texts = {k: clean_text(data[k]) for k in KINDS}
    except (KeyError, TypeError):
        return None
    if len(set(texts.values())) != 3 or not all(_ok_text(t) for t in texts.values()):
        return None
    correct, other = texts["correct"], texts["other"]
    if not (any(m in correct for m in SAFE_MARKERS) or any(a in correct for a in ADULT_WORDS)):
        return None  # 정답인데 조심하는 말이 없음
    if any(r in other for r in _REFUSAL):
        return None  # 다른 답인데 거절하고 있음
    return texts


def arrange(texts: dict) -> list[Choice]:
    order = sorted(KINDS, key=lambda k: hashlib.sha1(texts[k].encode("utf-8")).hexdigest())
    return [Choice(id=f"c{i}", text=texts[k], kind=k) for i, k in enumerate(order, start=1)]
