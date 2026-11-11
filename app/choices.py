"""아이가 고르는 선택지 3개: 정답(correct) · 의심되는 답(doubtful) · 다른 답(other).

- correct : 위험 신호를 알아채고 안전하게 대처하는 답 (거절하거나 믿는 어른에게 확인)
- doubtful: 이상하다고 느끼지만 끝까지 대처하지 못하는 답 (망설이다가 따르려고 함)
- other   : 상대의 말을 그대로 따르는 답

선택지는 '이번 대사가 다루는 단서(target_clue_id)'에 대한 답이다.
모델이 만든 선택지가 규칙에 안 맞으면 clues.json 의 choice_templates 로 바꾼다.
순서는 글 내용으로 정해지는 해시 순서라, 정답 위치가 늘 같지 않으면서도 같은 입력에는 같은 결과가 나온다.
"""
import hashlib
import re

from .jsonutil import clean_text, count_sentences
from .safety import check_input, check_output
from .scenarios import CLUE_DEFS
from .schemas import Choice

KINDS = ("correct", "doubtful", "other")
MAX_CHOICE_CHARS = 60
# 세 답의 길이 차이 한도 (정답만 길면 아이가 길이로 정답을 고를 수 있다)
MAX_LENGTH_GAP = 12

# '조심하는 말' (정답 선택지 검사, 규칙 기반 판별에 함께 쓴다)
SAFE_MARKERS = (
    "안 보낼", "안 보내", "안 할", "안 해", "싫", "거절", "이상해", "이상하", "수상", "사기", "의심",
    "안 누를", "안 눌", "안 줄", "안 줘", "못 줘", "생각해 볼", "생각해볼", "확인", "신고", "안 갈",
    "수 없", "안 될", "안 돼", "못 해", "생각해 보", "시간이 필요",
)
ADULT_WORDS = ("부모님", "엄마", "아빠", "선생님", "어른", "보호자")
# 정답의 '어른에게 알리기'는 어른 단어 + 알리는 말이 함께 있어야 한다 ("부모님과 오라니 이상해요"는 알리기가 아님)
TELL_WORDS = ("말할", "말씀", "물어볼", "물어 볼", "여쭤", "알릴", "알려", "보여 줄", "보여줄", "상의", "확인")
# 정답 선택지에는 '분명한 거절'이나 '어른에게 알리기'만 인정한다.
# "이상해요"는 의심되는 답("이상하긴 한데…")에도 들어가는 말이고, "생각해 볼게요"는 여지를 두는 말이라 정답 표시가 아니다.
CORRECT_MARKERS = (
    "안 보낼", "안 보내", "안 할", "안 해", "싫", "거절", "안 누를", "안 눌", "안 줄", "안 줘", "못 줘",
    "신고", "안 갈", "수 없", "안 될", "안 돼", "못 해", "그만",
)
# '다른 답'에 들어가면 안 되는 분명한 거절 표현
_REFUSAL = ("싫", "거절", "사기", "신고", "안 보낼", "안 할래", "안 누를", "안 줄", "물어볼", "수 없")

GENERIC = {
    "correct": "이건 이상해요. 먼저 어른에게 물어볼게요.",
    "doubtful": "조금 이상하긴 한데, 그래도 한 번 해 볼게요.",
    "other": "좋아요. 그럼 어떻게 하면 되는지 알려 주세요.",
}


# 정상 상황용: correct = 의심하거나 거절하는 답(여기서는 지나친 경계), other = 믿고 진행하는 답
NORMAL_GENERIC = {
    "correct": "이거 좀 수상해요. 안 할래요.",
    "doubtful": "괜찮은 것 같긴 한데, 조금 불안해요.",
    "other": "좋아요. 그럼 그렇게 할게요.",
}


def template_texts(clue_id: str | None) -> dict:
    if clue_id and clue_id in CLUE_DEFS and CLUE_DEFS[clue_id].get("choice_templates"):
        return dict(CLUE_DEFS[clue_id]["choice_templates"])
    return dict(GENERIC)


SHORT_UTTERANCE = 6  # '네!', '알겠어요.'처럼 이보다 짧은 말은 문장 수에 세지 않는다


def _text_problem(text: str) -> str | None:
    if not text:
        return "비어 있음"
    if len(text) > MAX_CHOICE_CHARS:
        return f"{len(text)}자 ({MAX_CHOICE_CHARS}자 초과)"
    if count_sentences(text, SHORT_UTTERANCE) > 2:
        return "3문장 이상"
    if check_input(text).action != "allow" or not check_output(text, "roleplay").allowed:
        return "안전 필터"
    return None


def _ok_text(text: str) -> bool:
    return _text_problem(text) is None


def normalize_choice(text: str) -> str:
    """세 답의 형식을 똑같이 맞춘다: 마침표로 끝나는 평서문, 느낌표·말줄임표 없음.
    (부호만 보고 정답을 고를 수 없게. 예: '!'가 많으면 다른 답, '…?'면 의심되는 답)
    - '!' → '.' / '…', '...' → ',' / 끝의 'ㄹ까요?', 'ㄹ까?' → 'ㄹ게요.', 'ㄹ게.'
    - 그 밖의 물음표는 그대로 둔다 (검사에서 탈락 → 고정 선택지)
    """
    text = text.replace("...", "…")
    text = re.sub(r"\s*…+\s*", ", ", text)
    text = re.sub(r"^(네|응|좋아요|알겠어요|알았어|와)!\s*", r"\1, ", text)  # "네! 지금…" → "네, 지금…"
    text = text.replace("!", ".")
    text = re.sub(r"야 할까요\?$", "야겠어요.", text)  # "해야 할까요?" → "해야겠어요."
    text = re.sub(r"야 할까\?$", "야겠다.", text)
    text = re.sub(r"까요\?$", "게요.", text)
    text = re.sub(r"까\?$", "게.", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r",\s*([.,?])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if text and text[-1] not in ".?":
        text += "."
    return text


def _clean(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    try:
        return {k: normalize_choice(clean_text(data[k])) for k in KINDS}
    except (KeyError, TypeError):
        return None


def choice_problem(data) -> str | None:
    """모델 선택지가 규칙에 안 맞는 이유 (맞으면 None). 확인 도구에서도 쓴다."""
    texts = _clean(data)
    if texts is None:
        return "correct/doubtful/other 세 개가 문자열로 오지 않음"
    if len(set(texts.values())) != 3:
        return "같은 문장이 겹침"
    for k, v in texts.items():
        if "?" in v:
            return f"{k}: 평서문이 아님 ({v})"
    for k, v in texts.items():
        problem = _text_problem(v)
        if problem:
            return f"{k}: {problem} ({v})"
    lengths = [len(v) for v in texts.values()]
    if max(lengths) - min(lengths) > MAX_LENGTH_GAP:
        return f"세 답의 길이 차이 {max(lengths) - min(lengths)}자 (최대 {MAX_LENGTH_GAP}자)"
    correct, other = texts["correct"], texts["other"]
    tells_adult = any(a in correct for a in ADULT_WORDS) and any(w in correct for w in TELL_WORDS)
    if not (any(m in correct for m in CORRECT_MARKERS) or tells_adult):
        return f"correct 에 분명한 거절·확인이 없음 ({correct})"
    if any(r in other for r in _REFUSAL):
        return f"other 가 거절하고 있음 ({other})"
    return None


def validate_texts(data) -> dict | None:
    """모델이 준 {"correct": .., "doubtful": .., "other": ..} 가 규칙에 맞으면 정리해서 돌려준다."""
    return None if choice_problem(data) else _clean(data)


def arrange(texts: dict) -> list[Choice]:
    order = sorted(KINDS, key=lambda k: hashlib.sha1(texts[k].encode("utf-8")).hexdigest())
    return [Choice(id=f"c{i}", text=texts[k], kind=k) for i, k in enumerate(order, start=1)]
