# ai 레포 (포트 8081)

백엔드(8080)가 내부 API로 호출하는 상태 없는 HTTP 서비스입니다. 점수·집계·다음 문제 선택은 백엔드 몫이고, 여기서는 글(대사·피드백·요약)만 만듭니다.

## 실행

```bash
pip install -r requirements.txt
make test        # 테스트 러너 (스모크 포함)
make run         # 로컬 서버: Fake 제공자, 토큰 dev-token
```

환경 변수는 `.env.example` 참고. `AI_INTERNAL_TOKEN` 이 없으면 서버가 뜨지 않습니다.

## API (현재)

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/health` | 없음 | 상태 확인 |
| POST | `/internal/v1/summary` | `X-Internal-Token` | T-75 보호자 학습 요약 |
| POST | `/internal/v1/practice/start` | `X-Internal-Token` | T-12 첫 대사 |
| POST | `/internal/v1/practice/turn` | `X-Internal-Token` | T-12 다음 턴 (안전 필터 포함) |
| POST | `/internal/v1/practice/variant` | `X-Internal-Token` | T-13 단서 고정 변형 (결과를 start/turn/judge/feedback 의 `variant` 로 그대로 보냄) |
| POST | `/internal/v1/practice/judge` | `X-Internal-Token` | T-14 단서 판별 (found / missed / not_shown) |
| POST | `/internal/v1/practice/feedback` | `X-Internal-Token` | T-14 쉬운 말 피드백 (판별 결과를 받아 문장만 생성) |
| POST | `/internal/v1/practice/setup` | `X-Internal-Token` | T-32 진단 결과 → 시작 난이도, 자주 쓰는 앱 → 연습 플랫폼 |
| POST | `/internal/v1/practice/deep/feedback` | `X-Internal-Token` | T-78 심화 연습: 아이가 쓴 판단 이유에 피드백 1~3문장 (점수 없음) |

요청·응답 샘플은 `contracts/` 의 JSON 입니다. 백엔드와 같은 파일로 테스트하세요.

- **아이 입력은 선택지 3개**입니다. `start`·`turn` 응답의 `choices`에 정답(`correct`)·의심되는 답(`doubtful`)·다른 답(`other`)이 섞인 순서로 옵니다. `kind`는 화면에 보여 주지 마세요.
- 아이가 고른 선택지는 다음 `turn`·`judge` 요청의 아이 메시지에 `text`, `choice_kind`, `clue_id`(그 응답의 `target_clue_id`)로 넣어 주세요. `judge`는 이 기록으로 판정합니다(정답 = 찾음, 나머지 = 놓침).
- **정상 상황**도 같은 `start`·`turn`·`judge`로 돌아갑니다. `scenario_id`에 정상 상황 id(`normal_cafe_01` 등 8개, `content/scenarios/scam.json`의 `normal_situations`)를 넣으세요. 단서가 없어서 `revealed_clue_ids`는 늘 빈 목록입니다.
- `judge` 응답의 `normal_outcome`: 정상 상황에서 `correct`(의심·거절)를 한 번이라도 고르면 `over_warned`, 아니면 `trusted_correctly`. 위험 상황은 `null`.
- 아이 메시지에 `choice_kind`가 하나라도 있으면 `judge`의 `source`는 늘 `choices`입니다(모델 안 씀).
- 위험 상황에서 한 턴에 새로 드러나는 단서는 **최대 1개**입니다. 모델이 두 개를 드러내면 하나만 남기도록 대사를 줄이고, 안 되면 다시 생성합니다.
- 보호자 요약의 `growth_level`은 보내지 않는 것(`null`)이 기본입니다.
- **T-74 힌트**: `start`·`turn` 요청에 `hint_level`(0 없음 / 1 약함 / 2 중간 / 3 강함)을 넣으면 응답의 `hint`에 힌트 문장이 옵니다. 단계는 백엔드가 정합니다.
- **T-34 정상 상황 생성**: `variant`에 정상 상황 id를 넣으면 위험 표현 없이 말투와 내용만 바꾼 정상 상황이 옵니다. '믿을 수 있는 경로'가 안심 신호의 일부라 **플랫폼은 바꾸지 않습니다**(다른 플랫폼을 요청하면 422). `feedback`에 `normal_outcome`을 넣으면 `normal_feedback`(정상 상황 판정 문구)이 옵니다.
- **T-32**: `variant` 요청에 `favorite_apps`를 넣으면 그 앱에 맞는 플랫폼을 먼저 고릅니다. 앱 목록과 난이도 기준은 `content/setup.json`.
- **T-78 심화 연습**: `status`가 `safe_reply`이면 연습을 멈춰 주세요. 아이의 글은 저장하지 않습니다.
- **연습 종료는 백엔드가 판단**합니다. 단 `turn` 응답이 `status: "safe_reply"`이면 바로 멈춰 주세요(선택지도 비어 있음).
- 요약 실패 시 `200 {"summary": null}` — 백엔드는 요약 칸만 비웁니다.
- 입력 오류는 `422 {"error": "invalid_request", "fields": [...]}` — 입력 값은 응답에 담지 않습니다.

## 규칙

- 운영 로그에는 `메서드 경로 -> 상태코드`만 남깁니다. 프롬프트·출력·요청 본문은 남기지 않습니다 (미성년자 개인정보 보호).
- Gemini SDK(`google-genai`)는 `app/providers.py` 한 파일에서만 import 합니다.
- 안전 필터 규칙은 `app/safety.py`, 기준 사례는 `content/safety_cases.json`, 안내 문구는 `content/safety_messages.json` 입니다.
- 모델이 실패하거나 출력이 필터에 걸리면 1번 다시 시도하고, 그래도 안 되면 시나리오의 단서 대사로 이어 갑니다 (`source: fallback`).
- 새 엔드포인트는 `app/server.py` 의 `ROUTES` 에 한 줄 추가하고, `contracts/` 에 샘플과 테스트를 함께 넣습니다.
