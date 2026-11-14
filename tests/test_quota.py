"""사용량 한도 초과(429): 재시도하지 않고 바로 대체 문장으로 넘어간다."""
import pytest

from app.judge import Judge
from app.practice import PracticeEngine
from app.providers import QuotaExceeded, _is_quota_error
from app.schemas import FeedbackRequest, JudgeRequest, TurnRequest, VariantRequest
from app.variation import Variator

SID = "scam_dm_parttime_01"
MSGS = [{"role": "ai", "text": "안녕하세요!"}, {"role": "child", "text": "어떻게 해요?"}]


class Exhausted:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, *, json_mode=False):
        self.calls += 1
        raise QuotaExceeded()


@pytest.mark.parametrize("run", [
    lambda p: PracticeEngine(p).turn(TurnRequest(scenario_id=SID, messages=MSGS, revealed_clue_ids=["too_good_pay"])),
    lambda p: Variator(p).generate(VariantRequest(scenario_id=SID)),
    lambda p: Judge(p).judge(JudgeRequest(scenario_id=SID, messages=MSGS, revealed_clue_ids=["too_good_pay"])),
    lambda p: Judge(p).feedback(FeedbackRequest(scenario_id=SID, results=[{"clue_id": "too_good_pay", "result": "found"}])),
], ids=["turn", "variant", "judge", "feedback"])
def test_quota_error_is_not_retried(run):
    p = Exhausted()
    r = run(p)
    assert p.calls == 1 and r.source == "fallback"


class SdkError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code = code


def test_detects_quota_errors():
    assert _is_quota_error(SdkError(429))
    assert _is_quota_error(Exception("429 RESOURCE_EXHAUSTED. quota"))
    assert not _is_quota_error(SdkError(500, "server error"))
