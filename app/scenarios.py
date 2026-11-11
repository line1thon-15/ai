"""시나리오 찾기 + T-13 변형 검증. 연습·판별·피드백이 모두 같은 규칙으로 시나리오를 고른다."""
from .content import load_clues
from .safety import check_output
from .schemas import ClueVariant, AiRole, Variant

CLUE_DEFS = {c["id"]: c for c in load_clues()["clues"]}


class UnknownScenario(Exception):
    pass


class InvalidVariant(Exception):
    pass


def get_base(scenarios: dict, scenario_id: str) -> dict:
    try:
        return scenarios[scenario_id]
    except KeyError:
        raise UnknownScenario(scenario_id) from None


def has_clue_keyword(text: str, clue_id: str) -> bool:
    return any(k in text for k in CLUE_DEFS[clue_id].get("keywords", []))


def check_variant(base: dict, v: Variant) -> list[str]:
    """변형이 단서 틀을 지켰는지 확인한다. 문제 목록을 돌려준다 (비어 있으면 통과)."""
    problems = []
    if v.base_scenario_id != base["id"]:
        problems.append("base_scenario_id")
    if v.platform not in set(base["variation_axes"]["platform"]) | {base["platform"]}:
        problems.append("platform")
    if [c.id for c in v.clues] != [c["id"] for c in base["clues"]]:
        return problems + ["clue_ids"]  # 단서 목록·순서가 다르면 더 볼 필요 없음
    for vc, bc in zip(v.clues, base["clues"]):
        if vc.at_opening != bool(bc.get("at_opening")) or vc.reveal_when != bc["reveal_when"]:
            problems.append(f"timing:{vc.id}")
        if not has_clue_keyword(vc.reveal_line, vc.id):
            problems.append(f"clue_missing:{vc.id}")
        if vc.at_opening and not has_clue_keyword(v.opening_line, vc.id):
            problems.append(f"opening_missing:{vc.id}")
    for name, text in [("opening_line", v.opening_line), ("child_setup", v.child_setup), ("title", v.title),
                       ("ai_role", v.ai_role.name + " " + v.ai_role.persona),
                       *[(f"reveal_line:{c.id}", c.reveal_line) for c in v.clues]]:
        if not check_output(text, "roleplay").allowed:
            problems.append(f"unsafe:{name}")
    return problems


def base_as_variant(base: dict) -> Variant:
    """원본 시나리오를 변형 형식으로 (모델이 실패했을 때 대체용)."""
    return Variant(
        base_scenario_id=base["id"],
        platform=base["platform"],
        tone=base["ai_role"]["tone"],
        context=base["variation_axes"]["context"][0],
        title=base["title"],
        child_setup=base["child_setup"],
        opening_line=base["opening_line"],
        ai_role=AiRole(**base["ai_role"]),
        clues=[ClueVariant(id=c["id"], at_opening=bool(c.get("at_opening")), reveal_when=c["reveal_when"],
                           reveal_line=c["reveal_line"]) for c in base["clues"]],
    )


def resolve(scenarios: dict, scenario_id: str, variant: Variant | None = None) -> dict:
    """시나리오 id (+ 선택: 변형) → 연습에 쓸 시나리오 dict."""
    base = get_base(scenarios, scenario_id)
    if variant is None:
        return base
    if base.get("kind") == "normal" or check_variant(base, variant):  # 정상 상황은 변형이 없다
        raise InvalidVariant(scenario_id)
    return {
        **base,
        "platform": variant.platform,
        "title": variant.title,
        "child_setup": variant.child_setup,
        "opening_line": variant.opening_line,
        "ai_role": variant.ai_role.model_dump(),
        "clues": [c.model_dump() for c in variant.clues],
    }
