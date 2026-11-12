"""T-29 진단 3문항: 영역마다 1문항, 안전한 답은 1개, 쉬운 말."""
import json
from pathlib import Path

import pytest

from app.content import CONTENT_DIR, load_clues
from app.safety import check_output

DATA = json.loads((Path(CONTENT_DIR) / "diagnosis.json").read_text(encoding="utf-8"))
CLUES = load_clues()
QS = DATA["questions"]


def test_three_questions_one_per_area():
    assert len(QS) == 3
    assert sorted(q["area"] for q in QS) == sorted(a["id"] for a in CLUES["areas"])
    assert len({q["id"] for q in QS}) == 3


@pytest.mark.parametrize("q", QS, ids=lambda q: q["id"])
def test_question_is_well_formed(q):
    clue_areas = {c["id"]: c["areas"] for c in CLUES["clues"]}
    assert q["clue_ids"] and all(q["area"] in clue_areas[c] for c in q["clue_ids"])
    assert q["situation"] and q["question"]
    opts = q["options"]
    assert len(opts) == 3 and len({o["id"] for o in opts}) == 3
    assert [o["risky"] for o in opts].count(False) == 1, "안전한 답은 1개"
    lengths = [len(o["text"]) for o in opts]
    assert max(lengths) <= 32 and max(lengths) - min(lengths) <= 8, "답 길이가 비슷해야 정답이 티 나지 않음"
    for text in [q["situation"], q["question"], *(o["text"] for o in opts)]:
        assert check_output(text, "roleplay").allowed, text
