"""로컬 확인용: '피드백' 한 번을 실제 제공자(Gemini)로 돌려서
원본 출력과, 카드·마무리 문장이 쓰였는지(아니면 왜 고정 문장으로 바뀌었는지) 보여 준다.

    python scripts/debug_feedback.py                        # contracts/practice.feedback.request.json 사용
    python scripts/debug_feedback.py 다른요청.json

화면에만 출력하고 로그·파일에는 남기지 않는다 (개발용).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config, ConfigError, load_dotenv  # noqa: E402
from app.content import load_all_scenarios  # noqa: E402
from app.jsonutil import clean_text, first_sentences, parse_json_object  # noqa: E402
from app.judge import (MAX_CARD_SENTENCES, MAX_CLOSING_SENTENCES, build_feedback_prompt,  # noqa: E402
                       feedback_problem)
from app.providers import build_provider  # noqa: E402
from app.scenarios import resolve  # noqa: E402
from app.schemas import FeedbackRequest  # noqa: E402


def check(label: str, value, n: int) -> None:
    try:
        text = first_sentences(clean_text(value), n)
    except TypeError:
        print(f"  [X] {label}: 문자열이 아님")
        return
    problem = feedback_problem(text)
    mark = "OK" if problem is None else "X "
    print(f"  [{mark}] {label}: {text}" + ("" if problem is None else f"\n        → 고정 문장 사용 / 이유: {problem}"))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv(ROOT / ".env")
    try:
        cfg = Config.from_env()
        provider = build_provider(cfg)
    except ConfigError as e:
        sys.exit(f"설정 오류: {e}")
    print(f"provider: {cfg.provider} / model: {cfg.gemini_model}")

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "contracts" / "practice.feedback.request.json"
    req = FeedbackRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    s = resolve(load_all_scenarios(), req.scenario_id, req.variant)
    targets = [r for r in req.results if r.result in ("found", "missed")]
    if not targets:
        sys.exit("found/missed 결과가 없어서 모델을 부르지 않아요.")
    try:
        raw = provider.generate(build_feedback_prompt(s, targets, req.messages), json_mode=True)
    except Exception as e:
        sys.exit(f"[X] 호출 실패: {type(e).__name__}: {e}")
    print("--- 원본 출력 ---")
    print(raw)
    print("-----------------")
    data = parse_json_object(raw)
    if data is None:
        sys.exit("[X] JSON 형식이 아님 → 전부 고정 문장 사용")
    got = {c.get("clue_id"): c.get("text") for c in data.get("cards") or [] if isinstance(c, dict)}
    for t in targets:
        if t.clue_id not in got:
            print(f"  [X] {t.clue_id} ({t.result}): 카드가 없음 → 고정 문장 사용")
        else:
            check(f"{t.clue_id} ({t.result})", got[t.clue_id], MAX_CARD_SENTENCES)
    check("마무리 문장", data.get("closing_line"), MAX_CLOSING_SENTENCES)


if __name__ == "__main__":
    main()
