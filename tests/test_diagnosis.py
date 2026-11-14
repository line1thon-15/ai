"""T-29 진단 3문항: 피그마 Y2-1 자기 평가 형식, 백엔드 형식 {id, text, options:[{id, text, score}]}."""
import json
from pathlib import Path

import pytest

from app.content import CONTENT_DIR
from app.safety import check_output

DATA = json.loads((Path(CONTENT_DIR) / "diagnosis.json").read_text(encoding="utf-8"))
QS = DATA["questions"]


def test_top_level_fields_match_backend():
    """백엔드 진단 파일은 모르는 필드를 거부한다. 다른 콘텐츠 파일과 같은 version(v1)만 둔다."""
    assert set(DATA) == {"version", "questions"} and DATA["version"] == "v1"


def test_three_questions_with_unique_ids():
    assert len(QS) == 3
    assert [q["id"] for q in QS] == ["q1", "q2", "q3"]


@pytest.mark.parametrize("q", QS, ids=lambda q: q["id"])
def test_question_matches_backend_format(q):
    assert set(q) == {"id", "text", "options"}, "백엔드 형식과 같은 필드만"
    assert q["text"] and len(q["options"]) == 3
    for o in q["options"]:
        assert set(o) == {"id", "text", "score"}
        assert o["id"].startswith(q["id"] + "_"), "선택지 id 에 문항 id 를 포함"
        assert isinstance(o["score"], int)
    assert [o["text"] for o in q["options"]] == ["그래요", "가끔", "아니에요"]
    # 점수가 높을수록 안전한 편 (백엔드 임시 문항과 같은 방향)
    assert [o["score"] for o in q["options"]] == [0, 1, 2]
    assert check_output(q["text"], "roleplay").allowed


def test_score_range_for_backend():
    """백엔드가 합계로 난이도를 정하므로 합계 범위가 0~6 이어야 한다."""
    assert sum(min(o["score"] for o in q["options"]) for q in QS) == 0
    assert sum(max(o["score"] for o in q["options"]) for q in QS) == 6
