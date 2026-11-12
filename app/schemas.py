"""T-75 보호자 학습 요약: 입출력 스키마.

백엔드(T-76)가 G3 리포트를 열 때마다 계산값을 조립해서 보내고,
AI는 그 값을 문장으로만 옮긴다. 점수·수치는 AI가 만들지 않는다.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SummaryRequest(BaseModel):
    area: str = Field(description="연습 영역 이름. 예: 사기, 명의 빌려주기, 친구의 무리한 부탁")
    practice_count: int = Field(ge=0, description="이번 기간 연습 횟수")
    found_clues: list[str] = Field(default_factory=list, description="아이가 찾은 단서 이름")
    missed_clues: list[str] = Field(default_factory=list, description="아이가 놓친 단서 이름")
    growth_level: str | None = Field(
        default=None, description="백엔드가 계산한 영역별 성장 수준 라벨. 예: 시작 단계, 익숙해지는 중"
    )


class SummaryResponse(BaseModel):
    # AI 실패 시 None. 백엔드는 요약 칸만 비운다.
    summary: str | None


# ---- T-12 연습 대화 -----------------------------------------------------------

ChoiceKind = Literal["correct", "doubtful", "other"]


class Message(BaseModel):
    role: Literal["ai", "child"]
    text: str = Field(min_length=1, max_length=500)
    # 아이가 선택지를 골랐을 때: 고른 선택지의 kind 와 그 선택지가 다룬 단서(target_clue_id)
    choice_kind: ChoiceKind | None = None
    clue_id: str | None = Field(default=None, max_length=64)


class Choice(BaseModel):
    id: str  # c1, c2, c3 (응답 안에서만 의미 있음)
    text: str
    kind: ChoiceKind  # correct 정답 / doubtful 의심되는 답 / other 다른 답 (화면에는 보여 주지 않음)


# ---- T-13 단서 고정 변형 -------------------------------------------------------
# 단서 ID·순서·드러나는 때는 원본 시나리오와 같아야 한다. 겉모습(플랫폼·말투·맥락·대사)만 바뀐다.

class AiRole(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    persona: str = Field(min_length=1, max_length=300)
    tone: str = Field(min_length=1, max_length=100)


class ClueVariant(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    at_opening: bool = False
    reveal_when: str = Field(min_length=1, max_length=100)
    reveal_line: str = Field(min_length=1, max_length=200)


class Variant(BaseModel):
    base_scenario_id: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=40)
    tone: str = Field(min_length=1, max_length=100)
    context: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=80)
    child_setup: str = Field(min_length=1, max_length=300)
    opening_line: str = Field(min_length=1, max_length=200)
    ai_role: AiRole
    clues: list[ClueVariant] = Field(default_factory=list, max_length=10)  # 정상 상황 변형은 빈 목록


class VariantRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    # 비우면 시나리오의 variation_axes 에서 고른다.
    # T-32: 진단·자주 쓰는 앱은 백엔드가 플랫폼으로 바꿔서 platform 으로 보낸다 (AI 는 변환·난이도 계산을 하지 않음)
    platform: str | None = None
    tone: str | None = None
    context: str | None = None


class VariantResponse(BaseModel):
    variant: Variant
    source: Literal["model", "fallback"]  # fallback: 원본 시나리오 그대로


class StartRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    variant: Variant | None = None  # T-13 변형을 쓸 때 /practice/variant 응답을 그대로 보낸다
    hint_level: int = Field(default=0, ge=0, le=3)  # T-74: 0 없음 / 1 약함 / 2 중간 / 3 강함 (백엔드가 정함)


class StartResponse(BaseModel):
    status: Literal["ok"] = "ok"
    reply: str  # 첫 대사
    ai_role_name: str
    title: str
    child_setup: str  # 아이에게 보여 줄 상황 설명
    revealed_clue_ids: list[str]  # 첫 대사에서 이미 드러난 단서
    target_clue_id: str | None  # 선택지가 다루는 단서
    choices: list[Choice]  # 정답·의심·다른 답 3개 (순서 섞음)
    choices_source: Literal["model", "template", "none"]
    hint: str | None = None  # hint_level 을 보냈을 때만


class TurnRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    messages: list[Message] = Field(min_length=1, max_length=40)  # 마지막은 아이의 글
    # 백엔드가 지금까지 드러난 단서를 알려 주면 반복하지 않는다 (선택)
    revealed_clue_ids: list[str] = Field(default_factory=list, max_length=20)
    variant: Variant | None = None
    hint_level: int = Field(default=0, ge=0, le=3)

    @field_validator("messages")
    @classmethod
    def _last_is_child(cls, v):
        if v[-1].role != "child":
            raise ValueError("마지막 메시지는 아이의 글이어야 합니다")
        return v


class TurnResponse(BaseModel):
    status: Literal["ok", "safe_reply", "blocked"]
    reply: str
    revealed_clue_ids: list[str]
    all_clues_revealed: bool  # 종료 판단은 백엔드가 한다. 단 status=safe_reply 이면 바로 멈출 것
    target_clue_id: str | None
    choices: list[Choice]  # safe_reply 일 때는 빈 목록
    choices_source: Literal["model", "template", "none"]
    masked: bool  # 아이의 글에서 개인정보를 가렸는지
    source: Literal["model", "fallback", "fixed"]
    hint: str | None = None  # hint_level 을 보냈을 때만 (safe_reply 이면 없음)


# ---- T-14 단서 판별 + 피드백 -----------------------------------------------------
# 판별 결과는 범주값만 (점수는 백엔드가 계산). 피드백은 백엔드가 저장한 판별 결과를 받아 문장만 만든다.

ClueResultValue = Literal["found", "missed", "not_shown"]


class ClueResult(BaseModel):
    clue_id: str = Field(min_length=1, max_length=64)
    result: ClueResultValue


class JudgeRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    messages: list[Message] = Field(min_length=1, max_length=40)  # 연습 대화 전체
    revealed_clue_ids: list[str] = Field(default_factory=list, max_length=20)
    variant: Variant | None = None


class JudgeResponse(BaseModel):
    results: list[ClueResult]  # 시나리오의 모든 단서, 시나리오 순서. 안 드러난 단서는 not_shown
    # choices: 아이가 고른 선택지로 판정 (모델 안 씀) / model·fallback: 글로 쓴 답을 판정
    source: Literal["choices", "model", "fallback", "fixed"]
    # 정상 상황에서만: correct(의심·거절)를 한 번이라도 고르면 over_warned, 아니면 trusted_correctly. 위험 상황은 null
    normal_outcome: Literal["trusted_correctly", "over_warned"] | None = None


class FeedbackRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    results: list[ClueResult] = Field(default_factory=list, max_length=20)  # 정상 상황은 빈 목록
    # T-34: 정상 상황이면 judge 의 normal_outcome 을 그대로 보내면 판정 문구(normal_feedback)를 만든다
    normal_outcome: Literal["trusted_correctly", "over_warned"] | None = None
    messages: list[Message] = Field(default_factory=list, max_length=40)  # 선택: 아이 말에 맞춘 피드백용
    variant: Variant | None = None


class FeedbackCard(BaseModel):
    clue_id: str
    result: Literal["found", "missed"]
    text: str


class FeedbackResponse(BaseModel):
    cards: list[FeedbackCard]  # found/missed 단서만, 요청 순서대로
    closing_line: str
    source: Literal["model", "fallback", "mixed", "fixed"]  # mixed: 일부 카드는 고정 문장
    normal_feedback: str | None = None  # T-34: 정상 상황 판정 문구 (위험 상황은 null)


# ---- T-78 심화 연습 피드백 -------------------------------------------------------

class DeepFeedbackRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    answer: str = Field(min_length=1, max_length=500)  # 아이가 쓴(또는 말로 해서 글자로 바꾼) 판단 이유
    question: str | None = Field(default=None, max_length=200)  # 화면에서 아이에게 한 질문 (선택)
    clue_ids: list[str] = Field(default_factory=list, max_length=20)  # 이번 연습에서 드러난 단서 (비우면 시나리오 전체)
    variant: Variant | None = None


class DeepFeedbackResponse(BaseModel):
    status: Literal["ok", "safe_reply", "blocked"]  # safe_reply 이면 연습을 멈출 것
    feedback: list[str]  # 1~3문장, 점수 없음
    masked: bool  # 아이의 글에서 개인정보를 가렸는지
    source: Literal["model", "fallback", "fixed"]
