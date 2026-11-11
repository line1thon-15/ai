"""T-75 보호자 학습 요약 문장 생성.

- 입력: 백엔드가 계산한 값 (SummaryRequest)
- 출력: 보호자용 1~2문장. 실패하면 None (백엔드는 요약 칸만 비움)
- 운영 로그에 프롬프트·출력 본문을 남기지 않는다 (AI-2).
"""
import re

from .jsonutil import clean_text
from .providers import LLMProvider
from .safety import check_output
from .schemas import SummaryRequest

MAX_SENTENCES = 2
MAX_CHARS = 200

_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|(?<=요)\s+(?=[가-힣])")
_NUMBER = re.compile(r"\d+")


def build_prompt(req: SummaryRequest) -> str:
    found = ", ".join(req.found_clues) or "없음"
    missed = ", ".join(req.missed_clues) or "없음"
    level = req.growth_level or "정보 없음"
    return (
        "너는 경계선 지능 청소년의 생활 판단 연습을 돕는 서비스에서 보호자에게 학습 내용을 알려 주는 역할이야.\n"
        "아래 기록만 바탕으로 보호자가 읽을 요약을 쓰되, 규칙을 지켜.\n"
        "- 1~2문장, 쉬운 말, 존댓말 대신 '~해요' 체.\n"
        "- 잘한 점을 먼저 말하고, 다음에 연습하면 좋을 점을 한 가지만 부드럽게 제안해.\n"
        "- 아이를 평가하거나 비난하지 말고, 진단·병명·점수·순위 표현은 쓰지 마.\n"
        "- 아래에 없는 숫자나 사실을 만들지 마.\n"
        "- 아이가 한 말·쓴 글을 인용하지 마.\n"
        "- 요약 문장만 출력해. 제목·따옴표·목록 없이.\n\n"
        f"영역: {req.area}\n"
        f"연습 횟수: {req.practice_count}\n"
        f"찾은 단서: {found}\n"
        f"놓친 단서: {missed}\n"
        f"성장 수준: {level}\n"
    )


def _allowed_numbers(req: SummaryRequest) -> set[str]:
    text = " ".join([req.area, str(req.practice_count), *req.found_clues, *req.missed_clues, req.growth_level or ""])
    return set(_NUMBER.findall(text))


def clean_summary(raw: str, req: SummaryRequest) -> str | None:
    """모델 출력을 검증·정리한다. 쓸 수 없으면 None."""
    text = clean_text(raw or "")
    if not text:
        return None
    # 비난·진단명·점수 표현이 섞이면 버린다 (아이 피드백과 같은 기준)
    if not check_output(text, "feedback").allowed:
        return None

    # 입력에 없는 숫자가 나오면 버린다 (성장 수치는 AI가 만들지 않음)
    if not set(_NUMBER.findall(text)) <= _allowed_numbers(req):
        return None

    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    text = " ".join(sentences[:MAX_SENTENCES])
    if len(text) > MAX_CHARS:
        return None
    return text


def generate_summary(req: SummaryRequest, provider: LLMProvider) -> str | None:
    try:
        raw = provider.generate(build_prompt(req))
    except Exception:
        # 본문을 로그에 남기지 않기 위해 예외 내용은 버린다
        return None
    return clean_summary(raw, req)
