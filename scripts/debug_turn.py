"""로컬 확인용: '다음 턴' 한 번을 실제 제공자(Gemini)로 돌려서
원본 출력과 어느 검사에서 떨어졌는지 화면에 보여 준다.

    python scripts/debug_turn.py                        # contracts/practice.turn.request.json 사용
    python scripts/debug_turn.py 다른요청.json
    python scripts/debug_turn.py samples/turn.game.json --repeat 5   # 5번 돌려서 탈락 이유 모으기

화면에만 출력하고 로그·파일에는 남기지 않는다. 아이의 실제 대화로는 쓰지 말 것 (개발용).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.choices import choice_problem  # noqa: E402
from app.config import Config, ConfigError, load_dotenv  # noqa: E402
from app.jsonutil import clean_text, count_sentences, parse_json_object  # noqa: E402
from app.practice import MAX_ATTEMPTS, MAX_RAW_REPLY_CHARS, MAX_REPLY_CHARS, PracticeEngine, _parse, shorten  # noqa: E402
from app.scenarios import has_clue_keyword  # noqa: E402
from app.providers import build_provider  # noqa: E402
from app.safety import check_output  # noqa: E402
from app.schemas import TurnRequest  # noqa: E402


def why_reply_rejected(raw: str) -> str:
    data = parse_json_object(raw)
    if data is None:
        return "JSON 형식이 아님"
    try:
        reply = clean_text(data.get("reply"))
    except TypeError:
        return "reply 가 없거나 문자열이 아님"
    if not reply:
        return "reply 가 비어 있음"
    if len(reply) > MAX_RAW_REPLY_CHARS:
        return f"대사가 {len(reply)}자 ({MAX_RAW_REPLY_CHARS}자 초과)"
    return "알 수 없음"


def evaluate(raw: str, valid_ids, revealed):
    """(대사 결과, 선택지 탈락 이유 또는 None, 최종 대사)"""
    parsed = _parse(raw, valid_ids)
    if parsed is None:
        return f"대사 탈락: {why_reply_rejected(raw)}", None, None
    full, claimed, choices = parsed
    new_ids = [i for i in valid_ids if i in claimed and i not in revealed and has_clue_keyword(full, i)]
    keep, dropped = new_ids[:1], new_ids[1:]
    reply = shorten(full, keep, dropped)
    if reply is None or any(has_clue_keyword(reply, d) for d in dropped):
        return "대사 탈락: 새 단서 1개만 남기도록 줄일 수 없음", None, None
    if len(reply) > MAX_REPLY_CHARS:
        return f"대사 탈락: {len(reply)}자", None, None
    out = check_output(reply, "roleplay")
    if not out.allowed:
        return f"대사 탈락: 안전 필터 {out.category}", None, None
    return "대사 OK", choice_problem(choices), reply


def repeat(provider, prompt, valid_ids, revealed, n: int) -> None:
    from collections import Counter
    reasons = Counter()
    ok = 0
    for i in range(1, n + 1):
        try:
            raw = provider.generate(prompt, json_mode=True)
        except Exception as e:
            print(f"[{i}] 호출 실패: {type(e).__name__}")
            reasons["호출 실패"] += 1
            continue
        reply_state, problem, reply = evaluate(raw, valid_ids, revealed)
        if reply_state != "대사 OK":
            print(f"[{i}] {reply_state}")
            reasons[reply_state] += 1
            continue
        choices = (parse_json_object(raw) or {}).get("choices")
        if problem is None:
            ok += 1
            print(f"[{i}] 대사·선택지 OK | {reply}")
        else:
            print(f"[{i}] 선택지 탈락: {problem}")
            reasons[re.sub(r"\d+", "N", problem.split(" (")[0])] += 1
        if isinstance(choices, dict):
            print("      " + " / ".join(f"{k}: {v}" for k, v in choices.items()))
    print(f"\n결과: {n}번 중 대사·선택지 모두 통과 {ok}번")
    for reason, count in reasons.most_common():
        print(f"  - {reason}: {count}번")


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

    args = sys.argv[1:]
    times = 1
    if "--repeat" in args:
        i = args.index("--repeat")
        times = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    path = Path(args[0]) if args else ROOT / "contracts" / "practice.turn.request.json"
    req = TurnRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    engine = PracticeEngine(provider)
    s = engine._scenario(req.scenario_id, req.variant)
    valid_ids = [c["id"] for c in s["clues"]]
    revealed = [i for i in req.revealed_clue_ids if i in valid_ids]
    normal = s.get("kind") == "normal"
    prompt = engine._build_normal_prompt(s, req) if normal else engine._build_prompt(s, revealed, req)
    print(f"시나리오: {req.scenario_id} ({'정상 상황' if normal else '위험 상황'})")

    if times > 1:
        repeat(provider, prompt, valid_ids, revealed, times)
        return

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n===== 시도 {attempt} =====")
        try:
            raw = provider.generate(prompt, json_mode=True)
        except Exception as e:
            print(f"[X] Gemini 호출 실패: {type(e).__name__}: {e}")
            continue
        print("--- 원본 출력 ---")
        print(raw)
        print("-----------------")
        parsed = _parse(raw, valid_ids)
        if parsed is None:
            print(f"[X] 대사 검사 탈락: {why_reply_rejected(raw)}")
            continue
        full, claimed, choices = parsed
        new_ids = [i for i in valid_ids if i in claimed and i not in revealed and has_clue_keyword(full, i)]
        keep, dropped = new_ids[:1], new_ids[1:]
        reply = shorten(full, keep, dropped)
        print(f"원래 문장 수: {count_sentences(full)} → 줄인 대사: {reply}")
        print(f"모델이 말한 단서: {claimed} / 인정된 새 단서(한 턴 1개): {keep} / 뺀 단서: {dropped}")
        if reply is None or any(has_clue_keyword(reply, d) for d in dropped):
            print("[X] 새 단서 1개만 남기도록 줄일 수 없음")
            continue
        if len(reply) > MAX_REPLY_CHARS:
            print(f"[X] 줄여도 {len(reply)}자 ({MAX_REPLY_CHARS}자 초과)")
            continue
        out = check_output(reply, "roleplay")
        print(f"출력 안전 필터: {out.action} {out.category or ''}")
        problem = choice_problem(choices)
        print("선택지 검사:", "통과 (choices_source=model)" if problem is None else f"탈락 → 고정 선택지 사용 / 이유: {problem}")
        if out.allowed:
            print("\n[OK] 이 출력이면 서버 응답은 source=model 이에요.")
            return
        print("[X] 출력 안전 필터에 걸림")
    print(f"\n→ {MAX_ATTEMPTS}번 다 탈락해서 서버는 fallback 을 씁니다.")


if __name__ == "__main__":
    main()
