"""T-13 단서 고정 변형 생성.

원본 시나리오의 단서(무엇을, 어떤 순서로, 언제 드러내는지)는 그대로 두고
플랫폼·말투·맥락과 대사만 바꾼 새 상황을 만든다.

- 플랫폼·말투·맥락은 코드가 고르고(variation_axes 안에서), 모델은 글만 쓴다.
- 단서 ID·순서·드러나는 때는 코드가 원본에서 복사한다. 모델은 바꿀 수 없다.
- 대사마다 단서 키워드가 남아 있는지, 안전 필터를 통과하는지 확인한다.
- 실패하면 1번 다시 시도하고, 그래도 안 되면 원본 시나리오를 그대로 돌려준다 (source=fallback).
"""
import random

from pydantic import ValidationError

from .content import load_all_scenarios
from .jsonutil import clean_text, parse_json_object
from .providers import LLMProvider, QuotaExceeded
from .scenarios import CLUE_DEFS, InvalidVariant, base_as_variant, check_variant, get_base
from .schemas import AiRole, ClueVariant, Variant, VariantRequest, VariantResponse

MAX_ATTEMPTS = 2

PLATFORM_NAMES = {
    "sns_dm": "SNS 쪽지(DM)",
    "open_chat": "오픈채팅",
    "text_message": "문자 메시지",
    "friend_intro": "아는 사람의 소개",
    "job_board": "채용 사이트 공고",
    "game_chat": "게임 속 채팅(귓속말)",
    "school_notice": "학교 알림장",
}


class InvalidAxis(Exception):
    def __init__(self, field: str):
        self.field = field


class Variator:
    def __init__(self, provider: LLMProvider, scenarios: dict | None = None, rng: random.Random | None = None):
        self.provider = provider
        self.scenarios = scenarios or load_all_scenarios()
        self.rng = rng or random.Random()

    def generate(self, req: VariantRequest) -> VariantResponse:
        base = get_base(self.scenarios, req.scenario_id)
        if base.get("kind") == "normal":  # 정상 상황은 변형하지 않는다
            raise InvalidVariant(req.scenario_id)
        axes = base["variation_axes"]
        for field in ("platform", "tone", "context"):
            value = getattr(req, field)
            if value is not None and value not in axes[field]:
                raise InvalidAxis(field)

        other_platforms = [p for p in axes["platform"] if p != base["platform"]] or axes["platform"]
        platform = req.platform or self.rng.choice(other_platforms)
        tone = req.tone or self.rng.choice(axes["tone"])
        context = req.context or self.rng.choice(axes["context"])

        prompt = build_prompt(base, platform, tone, context)
        for _ in range(MAX_ATTEMPTS):
            try:
                raw = self.provider.generate(prompt, json_mode=True)
            except QuotaExceeded:  # 한도 초과: 재시도해도 소용없음
                break
            except Exception:  # 내용은 남기지 않는다
                continue
            variant = to_variant(raw, base, platform, tone, context)
            if variant is not None:
                return VariantResponse(variant=variant, source="model")
        return VariantResponse(variant=base_as_variant(base), source="fallback")


def build_prompt(base: dict, platform: str, tone: str, context: str) -> str:
    lines = [
        "너는 경계선 지능 청소년의 생활 판단 연습 서비스에서, 연습 상황을 새로 바꿔 쓰는 작가야.",
        "아래 원본 상황의 '위험 신호(단서)'는 그대로 두고, 겉모습만 바꿔서 새 상황을 써.",
        "",
        f"[바꿀 플랫폼] {PLATFORM_NAMES.get(platform, platform)}",
        f"[바꿀 말투] {tone}",
        f"[바꿀 맥락] {context}",
        "",
        "[원본 상황]",
        f"- 제목: {base['title']}",
        f"- 상황 설명: {base['child_setup']}",
        f"- 상대 역할: {base['ai_role']['name']} — {base['ai_role']['persona']}",
        f"- 첫 대사: {base['opening_line']}",
        "",
        "[단서] 순서와 뜻을 바꾸지 마. 각 단서마다 새 대사를 하나씩 써.",
    ]
    for c in base["clues"]:
        d = CLUE_DEFS[c["id"]]
        opening = " (첫 대사에도 반드시 드러나야 함)" if c.get("at_opening") else ""
        lines.append(f"- {c['id']}: {d['description']}{opening} / 원본 대사: {c['reveal_line']}")
    lines += ["", "[규칙]"]
    lines += [f"- {r}" for r in base["ai_rules"]]
    lines += [
        "- 모든 글은 쉬운 말로, 대사는 1~2문장으로 써.",
        "- 단서를 빼거나 약하게 만들지 마. 새로운 위험 요소를 더하지도 마.",
        "- 실제 회사, 기관, 사람 이름은 쓰지 마.",
        "",
        "출력은 아래 JSON 한 개만 써. 다른 글은 쓰지 마.",
        '{"title": "새 제목", "child_setup": "아이에게 보여 줄 상황 설명 1~2문장", '
        '"ai_role": {"name": "상대 역할 이름", "persona": "성격 한 문장"}, '
        '"opening_line": "첫 대사", '
        '"clues": [{"id": "단서 id", "reveal_line": "그 단서를 드러내는 새 대사"}]}',
    ]
    return "\n".join(lines)


def to_variant(raw: str, base: dict, platform: str, tone: str, context: str) -> Variant | None:
    data = parse_json_object(raw)
    if data is None:
        return None
    try:
        lines = {c["id"]: clean_text(c["reveal_line"]) for c in data["clues"] if isinstance(c, dict)}
        variant = Variant(
            base_scenario_id=base["id"],
            platform=platform,
            tone=tone,
            context=context,
            title=clean_text(data["title"]),
            child_setup=clean_text(data["child_setup"]),
            opening_line=clean_text(data["opening_line"]),
            ai_role=AiRole(name=clean_text(data["ai_role"]["name"]), persona=clean_text(data["ai_role"]["persona"]),
                           tone=tone),
            clues=[ClueVariant(id=c["id"], at_opening=bool(c.get("at_opening")), reveal_when=c["reveal_when"],
                               reveal_line=lines.get(c["id"], "")) for c in base["clues"]],
        )
    except (KeyError, TypeError, ValidationError):
        return None
    return None if check_variant(base, variant) else variant
