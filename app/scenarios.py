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


# T-34: 정상 상황 변형에 들어가면 안 되는 위험 표현 (단서 키워드보다 좁게: '원', '지금' 같은 흔한 말은 뺀다)
NORMAL_RISK_PHRASES = (
    "오픈채팅", "모르는 사람", "모르는 계정", "입금", "보증금", "교육비", "수수료", "선입금", "송금", "계좌", "비밀번호", "신분증", "주민",
    "비밀로", "말하지 마", "말하면 안", "링크", "설치", "example.com", "당장", "빨리", "오늘까지", "오늘만",
    "빌려", "책임질",
    # 상대 관계·만나는 곳이 위험하게 바뀌는 표현 (실제 사례: '옆집 누나 … 우리 집으로 놀러 와')
    "우리 집", "집으로 와", "집으로 놀러", "놀러 와", "단둘이", "둘이서만", "혼자 와", "혼자서 와", "따로 만나", "따로 연락",
)
# 정상 상황 피드백·대사에서 상대를 '모르는 사람'으로 바꿔 부르는 표현
STRANGER_PHRASES = ("모르는 사람", "낯선 사람", "모르는 계정", "처음 보는 사람", "오픈채팅")


def _risky_use(text: str, phrase: str) -> bool:
    """'비밀번호는 묻지 않아요'처럼 바로 뒤에서 부정하면 위험 표현으로 보지 않는다."""
    start = text.find(phrase)
    while start != -1:
        tail = text[start + len(phrase):start + len(phrase) + 10]
        if "않" not in tail and "없" not in tail:
            return True
        start = text.find(phrase, start + 1)
    return False


def normal_base_text(base: dict) -> str:
    return " ".join([base["title"], base.get("child_setup", ""), base["opening_line"], base["ai_role"]["name"],
                     base["ai_role"]["persona"], base.get("summary", "")])


def normal_risk_hits(text: str, base: dict) -> list[str]:
    """정상 상황 글에 새로 들어온 위험 표현 (원본에 이미 있는 표현은 허용)."""
    base_text = normal_base_text(base)
    return [w for w in NORMAL_RISK_PHRASES if w not in base_text and _risky_use(text, w)]


def missing_keep(base: dict, text: str) -> list[str]:
    """원래 상황의 핵심 맥락·상대 관계(keep) 중 빠진 것."""
    return [g[0] for g in base.get("keep", []) if not any(w in text for w in g)]


def missing_signals(base: dict, text: str) -> list[str]:
    """안심 신호가 글에서 더 이상 성립하지 않는 것. 빈 목록인 신호('돈을 먼저 내라는 말이 없어요')는
    위험 표현 검사로 확인한다."""
    return [sig for sig, words in zip(base.get("safe_signals", []), base.get("signal_checks", []))
            if words and not any(w in text for w in words)]


def check_normal_variant(base: dict, v: Variant) -> list[str]:
    """정상 상황 변형: 단서가 없어야 하고, 위험 표현이 섞이면 안 된다."""
    problems = []
    if v.base_scenario_id != base["id"]:
        problems.append("base_scenario_id")
    if v.platform != base["platform"]:  # 정상 상황은 원래 플랫폼만
        problems.append("platform")
    if v.clues:
        problems.append("clue_ids")
    # 원본에 이미 있는 표현은 허용 (예: "고객센터는 비밀번호를 절대 묻지 않아요")
    for name, text in [("opening_line", v.opening_line), ("child_setup", v.child_setup), ("title", v.title),
                       ("ai_role", v.ai_role.name + " " + v.ai_role.persona)]:
        if not check_output(text, "roleplay").allowed:
            problems.append(f"unsafe:{name}")
        hits = normal_risk_hits(text, base)
        if hits:
            problems.append(f"risk_phrase:{name}:{hits[0]}")
    # 원래 상황의 핵심 맥락과 상대 관계가 남아 있어야 한다
    whole = " ".join([v.title, v.child_setup, v.opening_line, v.ai_role.name, v.ai_role.persona])
    problems += [f"keep_missing:{w}" for w in missing_keep(base, whole)]
    # 안심 신호는 아이가 보는 글(상황 설명 + 첫 대사)에서 성립해야 한다
    seen = v.child_setup + " " + v.opening_line
    problems += [f"signal_missing:{s}" for s in missing_signals(base, seen)]
    return problems


def check_variant(base: dict, v: Variant) -> list[str]:
    """변형이 단서 틀을 지켰는지 확인한다. 문제 목록을 돌려준다 (비어 있으면 통과)."""
    if base.get("kind") == "normal":
        return check_normal_variant(base, v)
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
        context=base["title"] if base.get("kind") == "normal" else base["variation_axes"]["context"][0],
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
    if check_variant(base, variant):
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
