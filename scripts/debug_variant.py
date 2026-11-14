"""로컬 확인용: 변형 생성을 실제 제공자(Gemini)로 돌려서, 원본 출력과 어느 검사에서 떨어졌는지 보여 준다.

    python scripts/debug_variant.py                         # contracts/practice.variant.request.json 사용
    python scripts/debug_variant.py 다른요청.json --repeat 3

화면에만 출력하고 로그·파일에는 남기지 않는다 (개발용).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from app.config import Config, ConfigError, load_dotenv  # noqa: E402
from app.content import load_all_scenarios  # noqa: E402
from app.jsonutil import clean_text, parse_json_object  # noqa: E402
from app.providers import build_provider  # noqa: E402
from app.scenarios import check_variant, get_base, opening_choices_problems  # noqa: E402
from app.schemas import AiRole, ClueVariant, OpeningChoices, Variant, VariantRequest  # noqa: E402
from app.variation import Variator, build_normal_prompt, build_prompt  # noqa: E402


def explain(raw: str, base: dict, platform: str, tone: str, context: str) -> list[str]:
    data = parse_json_object(raw)
    if data is None:
        return ["JSON 형식이 아님"]
    try:
        lines = {c["id"]: clean_text(c["reveal_line"]) for c in data.get("clues") or [] if isinstance(c, dict)}
        v = Variant(base_scenario_id=base["id"], platform=platform, tone=tone, context=context,
                    title=clean_text(data["title"]), child_setup=clean_text(data["child_setup"]),
                    opening_line=clean_text(data["opening_line"]),
                    ai_role=AiRole(name=clean_text(data["ai_role"]["name"]),
                                   persona=clean_text(data["ai_role"]["persona"]), tone=tone),
                    clues=[ClueVariant(id=c["id"], at_opening=bool(c.get("at_opening")), reveal_when=c["reveal_when"],
                                       reveal_line=lines.get(c["id"], "")) for c in base["clues"]])
    except (KeyError, TypeError, ValidationError) as e:
        return [f"필드 누락·형식 오류: {type(e).__name__}"]
    problems = check_variant(base, v)
    oc = data.get("opening_choices")
    if isinstance(oc, dict) and base.get("kind") != "normal":
        try:
            v.opening_choices = OpeningChoices(**{k: clean_text(oc[k]) for k in ("correct", "doubtful", "other")})
            problems += [f"(선택지만 빠짐) {p}" for p in opening_choices_problems(base, v)]
        except (KeyError, TypeError, ValidationError):
            problems.append("(선택지만 빠짐) 시작 선택지 형식 오류")
    return problems or ["통과"]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    repeat = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 1
    if "--repeat" in sys.argv:
        args = [a for a in args if a != str(repeat)]
    load_dotenv(ROOT / ".env")
    try:
        provider = build_provider(Config.from_env())
    except ConfigError as e:
        sys.exit(f"설정 오류: {e}")
    req = VariantRequest(**json.loads((ROOT / (args[0] if args else "contracts/practice.variant.request.json"))
                                      .read_text(encoding="utf-8")))
    base = get_base(load_all_scenarios(), req.scenario_id)
    platform = req.platform or base["platform"]
    tone = req.tone or base["variation_axes"]["tone"][0]
    context = req.context or base["variation_axes"]["context"][0]
    prompt = (build_normal_prompt(base, platform, tone, context) if base.get("kind") == "normal"
              else build_prompt(base, platform, tone, context))
    for n in range(1, repeat + 1):
        raw = provider.generate(prompt, json_mode=True)
        print(f"===== {n}번째 원본 출력 =====\n{raw}\n----- 검사 결과 -----")
        for p in explain(raw, base, platform, tone, context):
            print(" -", p)
        print()
    res = Variator(provider).generate(req)
    print(f"실제 /variant 결과: source={res.source}")


if __name__ == "__main__":
    main()
