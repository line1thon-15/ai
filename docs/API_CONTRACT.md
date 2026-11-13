# API 연동 명세

백엔드가 AI 서버를 부를 때 지켜야 할 규칙입니다. 요청·응답 샘플 JSON은 `contracts/`에 있고, 백엔드와 AI가 같은 파일로 테스트합니다.

## 엔드포인트

모든 `POST`는 `X-Internal-Token` 헤더가 필요합니다. `T-번호`는 팀 작업 분담표의 작업 번호입니다.

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/health` | 없음 | 상태 확인 |
| POST | `/internal/v1/practice/start` | `X-Internal-Token` | T-12 첫 대사 |
| POST | `/internal/v1/practice/turn` | `X-Internal-Token` | T-12 다음 턴 (안전 필터 포함) |
| POST | `/internal/v1/practice/variant` | `X-Internal-Token` | T-13 단서 고정 변형 / T-34 정상 상황 생성 |
| POST | `/internal/v1/practice/judge` | `X-Internal-Token` | T-14 단서 판별 |
| POST | `/internal/v1/practice/feedback` | `X-Internal-Token` | T-14 쉬운 말 피드백 |
| POST | `/internal/v1/summary` | `X-Internal-Token` | T-75 보호자 학습 요약 |
| POST | `/internal/v1/practice/deep/feedback` | `X-Internal-Token` | **(P2, 1차 MVP 밖)** T-78 판단 이유 피드백 |

```bash
curl -X POST http://127.0.0.1:8081/internal/v1/practice/start \
  -H "Content-Type: application/json" -H "X-Internal-Token: change-me" \
  -d @contracts/practice.start.request.json
```

## 연동 규칙

**선택지와 판별**
- 아이 입력은 **선택지 3개**입니다. `choices`의 `kind`는 `correct`(안전한 대응) / `doubtful`(망설이며 따르는 대응) / `other`(그대로 따르는 대응)이고, **화면에는 보여 주지 않습니다.**
- 아이가 고른 선택지는 다음 `turn`·`judge` 요청의 아이 메시지에 `text`, `choice_kind`, `clue_id`(그 응답의 `target_clue_id`)로 넣어 주세요. `judge`는 이 기록으로 판정합니다(`correct` = 찾음, 나머지 = 놓침, 모델 안 씀).
- 위험 상황에서 한 턴에 새로 드러나는 단서는 **최대 1개**입니다.

**대화 진행**
- 단서는 아이의 말에 맞춰 드러납니다. 단서마다 드러낼 때(`reveal_when`)와 아이 말의 신호(`triggers`, 예: '부모님께 물어볼게요' → 비밀 요구)가 있고, 모델이 실패해 준비된 대사로 이어 갈 때도 아이 말에 맞는 단서를 먼저 고릅니다.
- 모든 위험 상황은 **첫 대사에서 첫 단서를 드러냅니다.** `start`의 `revealed_clue_ids`와 `target_clue_id`에 그 단서가 들어 있고, 선택지도 그 단서에 반응합니다. 그래서 아이가 첫 선택에서 `correct`를 고르면 첫 단서를 찾은 것으로 판정되고, 백엔드는 지금 규칙대로 연습을 끝낼 수 있습니다.
- 아직 드러난 단서가 하나도 없는데 모델이 단서를 빠뜨리면, 다시 생성하고 그래도 없으면 준비된 단서 대사로 이어 갑니다.
- **연습 종료는 백엔드가 판단**합니다. 단 `status: "safe_reply"`가 오면 바로 멈춰 주세요(선택지도 비어 있음).
- **힌트(T-74):** `start`·`turn`에 `hint_level`(0 없음 / 1 약함 / 2 중간 / 3 강함)을 보내면 `hint`에 문장이 옵니다.

**상황 변형과 정상 상황**
- `variant` 결과는 `start`·`turn`·`judge`·`feedback`의 `variant`로 그대로 보내 주세요.
- 진단 점수·시작 난이도와 앱 → 플랫폼 변환은 **백엔드가 맡습니다(T-32).** AI는 받은 `platform`·`tone`·`context`로 문장만 만듭니다. 플랫폼 ID는 [콘텐츠 가이드](CONTENT_GUIDE.md#플랫폼-id)을 보세요.
- **정상 상황(T-34)**은 `scenario_id`에 정상 상황 id를 넣으면 같은 API로 돌아갑니다. `revealed_clue_ids`는 늘 빈 목록입니다.
  - `judge`의 `normal_outcome`: 한 번이라도 `correct`(의심·거절)를 고르면 `over_warned`, 아니면 `trusted_correctly`.
  - `feedback`에 `normal_outcome`을 넣으면 `normal_feedback`(판정 문구)이 옵니다.
  - '믿을 수 있는 경로'가 안심 신호의 일부라 **플랫폼은 바꾸지 않습니다**(다른 플랫폼 요청 시 422).
  - 생성 결과는 ① 원래 맥락·상대 관계(`keep`), ② 안심 신호가 실제로 성립하는지(`signal_checks`), ③ 새 위험 요구가 없는지 검사합니다. '비밀번호를 묻지 않아요' 같은 안전 안내는 허용하고 '비밀번호를 알려 주세요' 같은 요구는 막습니다. `turn` 대사와 판정 문구에도 같은 기준을 씁니다.

**응답 형식**
- 요약 실패 시 `200 {"summary": null}` — 요약 칸만 비워 주세요. `growth_level`은 보내지 않는 것이 기본입니다.
- 입력 오류는 `422 {"error": "invalid_request", "fields": [...]}` — 입력 값은 응답에 담지 않습니다.
- 없는 시나리오는 `404 scenario_not_found`, 틀이 맞지 않는 변형은 `422 invalid_variant`입니다.
- `source`로 결과가 어디서 왔는지 알 수 있습니다: `model`(Gemini) / `fallback`(준비된 문장) / `template`·`fixed`(고정 문장) / `choices`(선택 기록으로 판정).
