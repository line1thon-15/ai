"""T-32 진단 결과 → 시작 난이도, 자주 쓰는 앱 → 연습 플랫폼.

규칙은 content/setup.json 에 있다 (코드 수정 없이 앱·기준을 고칠 수 있게).
- 시작 난이도: 진단에서 위험한 답이 적으면 2단계, 많거나 모르면 1단계(쉬운 단계)부터
- 플랫폼: 자주 쓰는 앱을 연습 플랫폼(sns_dm, open_chat, text_message, game_chat, job_board)으로 바꾼다.
  변형 생성(/practice/variant)에 favorite_apps 를 주면 이 순서대로 플랫폼을 고른다.
"""
import json
import re

from .content import CONTENT_DIR
from .schemas import SetupRequest, SetupResponse

SETUP = json.loads((CONTENT_DIR / "setup.json").read_text(encoding="utf-8"))


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


_APP_INDEX = {}
for _app in SETUP["apps"]:
    for _n in [_app["name"], *_app["aliases"]]:
        _APP_INDEX[_norm(_n)] = _app["platforms"]


def platforms_for_apps(apps: list[str]) -> tuple[list[str], list[str]]:
    """(선호 플랫폼 순서, 모르는 앱 이름)"""
    platforms, unknown = [], []
    for name in apps:
        found = _APP_INDEX.get(_norm(name))
        if found is None:
            unknown.append(name)
            continue
        platforms += [p for p in found if p not in platforms]
    return platforms, unknown


def start_difficulty(risky_count: int | None) -> int:
    if risky_count is None:
        return 1
    return 2 if risky_count <= SETUP["difficulty"]["level_2_if_risky_at_most"] else 1


def plan(req: SetupRequest) -> SetupResponse:
    platforms, unknown = platforms_for_apps(req.favorite_apps)
    return SetupResponse(start_difficulty=start_difficulty(req.diagnosis_risky_count),
                         preferred_platforms=platforms, unknown_apps=unknown)
