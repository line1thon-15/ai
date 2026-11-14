"""입력·출력 안전 필터 (T-12). 규칙 기반이라 모델 없이도 동작하고, 결과가 늘 같다.

입력(아이가 쓴 글)
  safe_reply: 자해·폭력 피해 → 연습을 멈추고 고정 안내 문구
  block     : 욕설·성적 요청·규칙 우회 → 모델에 넘기지 않고 고정 문구
  mask      : 주민번호·전화·계좌·주소·학교 → 가린 뒤 모델에 넘김
  allow
출력(AI가 만든 글, speaker = roleplay | feedback)
  block: 진짜 같은 링크·번호, 사기 방법 설명, 폭력·성적 표현, 비난·진단명·점수,
         (feedback 만) 위험한 행동 권유
  allow

기준 데이터는 content/safety_cases.json (T-05). 규칙을 고치면 tests/test_safety.py 로 전체를 다시 확인한다.
"""
import json
import re
from dataclasses import dataclass

from .content import CONTENT_DIR

MESSAGES = json.loads((CONTENT_DIR / "safety_messages.json").read_text(encoding="utf-8"))
MASK = MESSAGES["masked_note"]


@dataclass(frozen=True)
class FilterResult:
    action: str  # allow | mask | safe_reply | block
    category: str | None = None
    text: str | None = None  # mask 일 때 가린 글

    @property
    def allowed(self) -> bool:
        return self.action == "allow"


def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns))


# ---- 입력 규칙 --------------------------------------------------------------

_SELF_HARM = _rx(r"죽고\s*싶", r"자살", r"자해", r"살기\s*싫", r"사라지고\s*싶", r"사라져\s*버리고\s*싶", r"없어지고\s*싶")
_VIOLENCE_VICTIM = _rx(r"때려요", r"때린다", r"때려서", r"때렸", r"맞았", r"괴롭혀", r"괴롭힘", r"폭력")
_PROFANITY = _rx(r"씨발", r"시발", r"ㅅㅂ", r"ㅆㅂ", r"병신", r"ㅂㅅ", r"개새", r"좆", r"꺼져", r"닥쳐", r"미친놈", r"미친년")
_SEXUAL = _rx(r"야한", r"섹스", r"성관계", r"야동", r"알몸", r"벗은\s*사진", r"음란")
_INJECTION = _rx(
    r"(규칙|지시|명령|설정|프롬프트)\S*\s*(다\s*)?(무시|잊)",
    r"너는\s*이제",
    r"역할을?\s*바꿔",
    r"시스템\s*프롬프트",
    r"속이는\s*(방법|법)",
    r"사기\s*치는\s*(방법|법)",
)

_PII = [
    re.compile(r"\d{6}\s*-\s*\d{7}"),                                      # 주민등록번호
    re.compile(r"01[016789]\s*-?\s*\d{3,4}\s*-?\s*\d{4}"),                 # 휴대전화
    re.compile(r"\d{2,6}-\d{2,6}-\d{2,8}"),                                # 계좌
    re.compile(r"\S+(구|군)\s+\S+(동|읍|면|로|길)(\s*\d+(-\d+)?\s*(번지)?)?"),  # 주소
    re.compile(r"\S+(초등학교|중학교|고등학교)(\s*\d+\s*학년)?(\s*\d+\s*반)?"),   # 학교·학년·반
]


def mask_pii(text: str) -> str:
    for rx in _PII:
        text = rx.sub(MASK, text)
    return text


def filter_input(text: str) -> FilterResult:
    if _SELF_HARM.search(text):
        return FilterResult("safe_reply", "self_harm")
    if _VIOLENCE_VICTIM.search(text):
        return FilterResult("safe_reply", "violence_victim")
    for category, rx in (("profanity", _PROFANITY), ("sexual", _SEXUAL), ("prompt_injection", _INJECTION)):
        if rx.search(text):
            return FilterResult("block", category)
    masked = mask_pii(text)
    if masked != text:
        return FilterResult("mask", "personal_info", masked)
    return FilterResult("allow")


# ---- 출력 규칙 --------------------------------------------------------------

_URL = re.compile(r"(https?://|www\.)\S+|\b[\w-]+(\.[\w-]+)*\.(com|net|org|kr|io|me|co)\b\S*")
_NUMBER_GROUPS = re.compile(r"\d{2,6}(\s*-\s*\d{2,8}){2,}")
_SCAM_HOWTO = _rx(r"속이려면", r"속이는\s*(방법|법)", r"사기\s*치는\s*(방법|법)", r"들키지\s*않(게|으려면)")
_VIOLENCE = _rx(r"때려\s*줄", r"때릴\s*거", r"죽여", r"죽일", r"가만\s*안\s*둘", r"칼로")
_BLAME = _rx(r"바보", r"멍청", r"한심", r"이해력이\s*부족", r"그것도\s*모르")
_DIAGNOSIS = _rx(r"경계선\s*지능", r"지적\s*장애", r"장애가\s*있", r"ADHD", r"자폐")
_SCORE = _rx(r"\d+\s*점", r"점수", r"등수", r"친구들보다\s*못")
_UNSAFE_ADVICE = _rx(
    r"(돈을|돈|송금|입금)\S*\s*(보내|해)\s*보세요",
    r"링크를?\s*눌러\s*보세요",
    r"(알려\s*줘도|보내도)\s*괜찮",
)


def _real_looking_contact(text: str) -> bool:
    for m in _URL.finditer(text):
        if not m.group(0).lstrip("(").startswith("example.com"):
            return True
    for m in _NUMBER_GROUPS.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if digits.startswith("010"):
            digits = digits[3:]
        if set(digits) != {"0"}:
            return True
    return False


def filter_output(text: str, speaker: str = "roleplay") -> FilterResult:
    if _real_looking_contact(text):
        return FilterResult("block", "real_looking_contact")
    checks = [
        ("scam_howto", _SCAM_HOWTO),
        ("violence", _VIOLENCE),
        ("sexual", _SEXUAL),
        ("blame", _BLAME),
        ("diagnosis", _DIAGNOSIS),
        ("score_compare", _SCORE),
    ]
    if speaker == "feedback":
        checks.append(("unsafe_advice", _UNSAFE_ADVICE))
    for category, rx in checks:
        if rx.search(text):
            return FilterResult("block", category)
    return FilterResult("allow")


# practice.py 등에서 쓰는 이름
check_input = filter_input
check_output = filter_output
