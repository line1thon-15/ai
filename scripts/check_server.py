"""켜져 있는 AI 서버에 기능별 요청을 한 번씩 보내고 결과를 한눈에 보여 주는 확인 도구.

    (창 1) python -m app
    (창 2) python scripts/check_server.py          # 요약만
           python scripts/check_server.py --full   # 응답 JSON 전체도 출력

토큰과 포트는 ai/.env 에서 읽는다. Gemini 를 쓰는 요청은 9번 정도다
(다음 턴 3, 변형 2, 피드백 2, 심화 1, 요약 1. 안전 확인 요청은 모델을 부르지 않는다).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import load_dotenv  # noqa: E402

# (이름, 경로, 요청 파일, 확인할 것)
CHECKS = [
    ("서버 상태", "GET", "/health", None, "status=ok"),
    ("첫 대사: 게임 아이템 사기", "POST", "/internal/v1/practice/start", {"scenario_id": "scam_game_item_01"}, "선택지 3개"),
    ("첫 대사: 용돈 이벤트 사기", "POST", "/internal/v1/practice/start", {"scenario_id": "scam_allowance_event_01"}, "선택지 3개"),
    ("첫 대사 + 힌트 2단계", "POST", "/internal/v1/practice/start", "contracts/practice.start.hint.request.json", "hint 문장"),
    ("진단·앱 반영 (T-32)", "POST", "/internal/v1/practice/setup", "contracts/practice.setup.request.json", "start_difficulty, 플랫폼"),
    ("다음 턴: 알바 사기", "POST", "/internal/v1/practice/turn", "contracts/practice.turn.request.json", "source=model"),
    ("다음 턴: 게임 아이템 사기", "POST", "/internal/v1/practice/turn", "samples/turn.game.json", "source=model, 새 단서 1개"),
    ("다음 턴: 정상 상황", "POST", "/internal/v1/practice/turn", "samples/turn.normal.json", "source=model, 단서 없음"),
    ("안전 확인: 자해 표현", "POST", "/internal/v1/practice/turn", "samples/turn.safe_reply.json", "status=safe_reply, 선택지 0개"),
    ("변형 생성", "POST", "/internal/v1/practice/variant", "contracts/practice.variant.request.json", "source=model"),
    ("정상 상황 생성 (T-34)", "POST", "/internal/v1/practice/variant", "contracts/practice.normal.variant.request.json", "source=model"),
    ("판별: 위험 상황", "POST", "/internal/v1/practice/judge", "contracts/practice.judge.request.json", "source=choices"),
    ("판별: 정상 상황", "POST", "/internal/v1/practice/judge", "contracts/practice.normal.judge.request.json", "normal_outcome"),
    ("피드백", "POST", "/internal/v1/practice/feedback", "contracts/practice.feedback.request.json", "source=model"),
    ("정상 상황 판정 문구 (T-34)", "POST", "/internal/v1/practice/feedback", "contracts/practice.normal.feedback.request.json", "source=model"),
    ("심화 연습 피드백 (T-78)", "POST", "/internal/v1/practice/deep/feedback", "contracts/practice.deep.feedback.request.json", "source=model"),
    ("심화 연습: 자해 표현", "POST", "/internal/v1/practice/deep/feedback", "samples/deep.safe_reply.json", "status=safe_reply"),
    ("보호자 요약", "POST", "/internal/v1/summary", "contracts/summary.request.json", "summary 문장"),
]


def call(base, token, method, path, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Internal-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def summarize(body: dict) -> str:
    parts = []
    for key in ("status", "source", "choices_source", "normal_outcome"):
        if key in body and body[key] is not None:
            parts.append(f"{key}={body[key]}")
    if "revealed_clue_ids" in body:
        parts.append(f"단서={body['revealed_clue_ids']}")
    if "choices" in body:
        parts.append(f"선택지 {len(body['choices'])}개")
    if "results" in body:
        parts.append("판별=" + ", ".join(f"{r['clue_id']}:{r['result']}" for r in body["results"]))
    if "start_difficulty" in body:
        parts.append(f"start_difficulty={body['start_difficulty']}  플랫폼={body['preferred_platforms']}")
    for key in ("reply", "hint", "summary", "closing_line", "normal_feedback"):
        if body.get(key):
            parts.append(f'\n      {key}: {body[key]}')
    if body.get("choices"):
        parts += [f"\n      [{c['kind']:8}] {c['text']}" for c in body["choices"]]
    if isinstance(body.get("feedback"), list):
        parts += [f"\n      - {s}" for s in body["feedback"]]
    if body.get("cards"):
        parts += [f"\n      [{c['result']:6}] {c['text']}" for c in body["cards"]]
    if body.get("variant"):
        v = body["variant"]
        parts.append(f"\n      {v['platform']} / {v['title']}\n      첫 대사: {v['opening_line']}")
    return "  ".join(parts)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv(ROOT / ".env")
    token = os.environ.get("AI_INTERNAL_TOKEN", "")
    base = f"http://127.0.0.1:{os.environ.get('AI_PORT', '8081')}"
    full = "--full" in sys.argv
    print(f"서버: {base} / provider: {os.environ.get('AI_PROVIDER', 'fake')}\n")
    for name, method, path, src, expect in CHECKS:
        body = json.loads((ROOT / src).read_text(encoding="utf-8")) if isinstance(src, str) else src
        try:
            status, res = call(base, token, method, path, body)
        except urllib.error.URLError:
            sys.exit("서버에 연결할 수 없어요. 다른 창에서 python -m app 으로 서버를 먼저 켜 주세요.")
        mark = "OK " if status == 200 else "ERR"
        print(f"[{mark}] {name}  (기대: {expect})\n      HTTP {status}  {summarize(res)}")
        if full:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
