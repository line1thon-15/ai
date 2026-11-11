"""로컬 확인용: '다음 턴' 한 번을 실제 제공자(Gemini)로 돌려서
원본 출력과 어느 검사에서 떨어졌는지 화면에 보여 준다.

    python scripts/debug_turn.py                        # contracts/practice.turn.request.json 사용
    python scripts/debug_turn.py 다른요청.json

화면에만 출력하고 로그·파일에는 남기지 않는다. 아이의 실제 대화로는 쓰지 말 것 (개발용).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.choices import validate_texts  # noqa: E402
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

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "contracts" / "practice.turn.request.json"
    req = TurnRequest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    engine = PracticeEngine(provider)
    s = engine._scenario(req.scenario_id, req.variant)
    valid_ids = [c["id"] for c in s["clues"]]
    revealed = [i for i in req.revealed_clue_ids if i in valid_ids]
    prompt = engine._build_prompt(s, revealed, req)

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
        new_ids = [i for i in claimed if has_clue_keyword(full, i)]
        reply = shorten(full, new_ids)
        print(f"원래 문장 수: {count_sentences(full)} → 줄인 대사: {reply}")
        print(f"모델이 말한 단서: {claimed} / 인정된 단서: {new_ids}")
        if len(reply) > MAX_REPLY_CHARS:
            print(f"[X] 줄여도 {len(reply)}자 ({MAX_REPLY_CHARS}자 초과)")
            continue
        out = check_output(reply, "roleplay")
        print(f"출력 안전 필터: {out.action} {out.category or ''}")
        print("선택지 검사:", "통과 (choices_source=model)" if validate_texts(choices) else "탈락 → 고정 선택지 사용")
        if out.allowed:
            print("\n[OK] 이 출력이면 서버 응답은 source=model 이에요.")
            return
        print("[X] 출력 안전 필터에 걸림")
    print(f"\n→ {MAX_ATTEMPTS}번 다 탈락해서 서버는 fallback 을 씁니다.")


if __name__ == "__main__":
    main()
