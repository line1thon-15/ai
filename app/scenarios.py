"""시나리오 찾기 + T-13 변형 검증. 연습·판별·피드백이 모두 같은 규칙으로 시나리오를 고른다."""
import re

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


# 위험 단어 뒤 '같은 마디' 안에서 부정하면 안전 안내로 본다 ('고객센터는 비밀번호를 절대 묻지 않아요')
_NEGATION = ("않", "없", "마세요", "말아", "금지")
# 부정처럼 보여도 실제로는 요구·협박인 표현 ('비밀번호를 알려 주지 않으면 계정이 막혀요')
_THREAT = ("않으면", "없으면", "안 하면", "안 그러면", "안 주면", "안 보내면")
# 요구하는 말 (뒤에 '-지 마/-지 않'이 바로 붙으면 그 요구를 부정하는 안내)
_REQUEST = ("알려", "보내", "입력", "적어", "말해", "넣어", "눌러", "찍어", "올려", "달라", "해 주", "해 줘", "하세요",
            "줘", "주세요", "주실", "주면", "줄래")
_NEGATED_REQUEST = re.compile(r"^\s*(주|해\s*주|해)?\s*지\s*(않|마|말)")
# 요구하는 말이 '~달라는 사람', '~보내라는 말'처럼 꾸미는 말로 쓰이면 요구가 아니다 (뒤의 부정이 그 말 전체를 부정)
_MODIFIER = re.compile(r"^\s*(달라|주라|해\s*달라|라|으라)?는\s")
_SENTENCE_END = re.compile(r"[.!?。\n]")
# 마디 경계: 쉼표나 이어 주는 말 뒤로는 다른 이야기다 ('알려 주세요, 잊지 마세요' 의 '마세요'는 비밀번호와 상관없음)
_CLAUSE_END = re.compile(r",|，|;| 그리고 | 그런데 | 근데 |지만 |는데 ")


def _has_live_request(clause: str) -> bool:
    """마디 안에 부정되지 않은 요구가 있는지 ('알려 주세요' → 있음, '알려 주지 마세요' → 없음)."""
    for verb in _REQUEST:
        start = clause.find(verb)
        while start != -1:
            after = clause[start + len(verb):]
            if not _NEGATED_REQUEST.match(after) and not _MODIFIER.match(after):
                return True
            start = clause.find(verb, start + 1)
    return False


def _is_safety_notice(tail: str) -> bool:
    """위험 단어 바로 뒤 마디(tail)가 그 단어를 부정하는 안내인지.
    1) 협박('않으면')이 있으면 요구  2) 부정되지 않은 요구('알려 주세요')가 있으면 요구
    3) 같은 마디 안에 부정('않', '없', '마세요')이 있으면 안내  4) 그 밖에는 요구로 본다."""
    clause = _CLAUSE_END.split(tail, maxsplit=1)[0]
    if any(w in clause for w in _THREAT):
        return False
    if _has_live_request(clause):
        return False
    if any(w in clause for w in _NEGATION):
        return True
    # '알려 주면 안 돼요'는 안내, '알려 주면 안 돼?'는 묻는 말이라 요구로 본다
    return ("안 돼" in clause or "안 되" in clause) and not clause.rstrip().endswith("?")


def _risky_use(text: str, phrase: str) -> bool:
    """위험 단어가 한 번이라도 '안전 안내'가 아닌 뜻으로 쓰였는지. 같은 단어가 여러 번 나오면 하나씩 본다."""
    start = text.find(phrase)
    while start != -1:
        rest = text[start + len(phrase):]
        end = _SENTENCE_END.search(rest)
        tail = rest[:end.end()] if end else rest
        # 다음에 같은 단어가 또 나오면 거기까지만 본다 ('묻지 않지만, 비밀번호를 알려 주세요')
        nxt = tail.find(phrase)
        if nxt != -1:
            tail = tail[:nxt]
        if not _is_safety_notice(tail):
            return True
        start = text.find(phrase, start + 1)
    return False


def normal_base_text(base: dict) -> str:
    return " ".join([base["title"], base.get("child_setup", ""), base["opening_line"], base["ai_role"]["name"],
                     base["ai_role"]["persona"], base.get("summary", "")])


def normal_risk_hits(text: str, base: dict | None = None) -> list[str]:
    """정상 상황 글(변형·대사·판정 문구)에 들어간 위험 요구.
    원본에 같은 단어가 있어도 허용하지 않는다. 단어 뒤에서 부정하는 안전 안내만 허용한다
    (백엔드 리뷰: 원본의 '비밀번호를 묻지 않아요' 때문에 '비밀번호를 알려 주세요'가 통과하면 안 됨)."""
    return [w for w in NORMAL_RISK_PHRASES if _risky_use(text, w)]


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
    # 원본에 같은 단어가 있어도 허용하지 않는다. '비밀번호를 절대 묻지 않아요'처럼 부정하는 안내만 허용
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
