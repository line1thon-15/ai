# SLOW:RE — AI 서버

[![ai-tests](https://github.com/line1thon-15/ai/actions/workflows/test.yml/badge.svg)](https://github.com/line1thon-15/ai/actions/workflows/test.yml)

> 경계선 지능 청소년(느린 학습자)이 생활 속 위험한 상황을 **AI와 안전하게 반복 연습**하도록 돕는 AI 서버입니다.

1호선톤 15조 **SLOW:RE**의 AI 파트 저장소입니다. 백엔드(8080)가 내부 API로 부르는 **상태 없는 HTTP 서버**(8081)로, **대화 생성, 위험 신호 판별, 피드백과 학습 요약**을 담당합니다. 점수 계산, 학습 기록 저장, 다음 문제 선택은 백엔드가 맡습니다.

## 목차

1. [프로젝트 소개](#1-프로젝트-소개)
2. [주요 기능](#2-주요-기능)
3. [AI 처리 흐름](#3-ai-처리-흐름)
4. [설치 및 실행](#4-설치-및-실행)
5. [API 명세](#5-api-명세)
6. [기능별 요청 예시](#6-기능별-요청-예시)
7. [콘텐츠 구성](#7-콘텐츠-구성)
8. [기술 스택과 AI 제공자](#8-기술-스택과-ai-제공자)
9. [폴더 구조](#9-폴더-구조)
10. [테스트](#10-테스트)
11. [안전 및 개인정보](#11-안전-및-개인정보)
12. [팀 및 참고 자료](#12-팀-및-참고-자료)

## 1. 프로젝트 소개

**SLOW:RE**는 일상 속 위험하거나 어려운 상황을 AI와 반복 연습하면서, 스스로 판단하고 대처하는 힘을 기르는 생활 자립 학습 서비스입니다.

경계선 지능 청소년은 개인에 따라 상대의 의도를 파악하거나 행동의 결과를 예측하는 데 어려움을 겪을 수 있습니다. 온라인 대화, 아르바이트, 친구 사이 돈 문제처럼 혼자 판단할 일은 늘어나지만, 지적장애와 구분되어 맞춤 지원을 받기 어려운 경우가 있습니다. 그래서 실제 피해를 겪기 전에 실패 부담 없이 연습할 수 있는 환경을 만들었습니다.

**AI 파트의 목표**는 정답을 외우게 하는 것이 아니라, 처음 보는 상황에서도 **위험 신호를 스스로 알아보게** 하는 것입니다.

- AI가 사기범·선배·친구 같은 **상대 역할을 연기**하며 위험 신호를 대화 속에서 하나씩 드러냅니다.
- 같은 위험 신호를 **다른 앱·말투·맥락**으로 바꿔, 외운 답이 아니라 판단 기준을 익히게 합니다.
- 위험 신호가 없는 **정상 상황**도 함께 내서, 믿어도 되는 상황을 구분하게 합니다.
- 틀려도 **비난하지 않고** 쉬운 말로 무엇을 놓쳤는지 알려 줍니다.

## 2. 주요 기능

1차 MVP에서 AI 파트가 맡은 기능입니다. Gemini는 **문장을 만드는 곳**에만 쓰고, 판정처럼 정확해야 하는 곳은 규칙으로 처리합니다.

| 기능 | 처리 방식 | 내용 |
|---|---|---|
| 상대 역할 대화 | Gemini | 아이 답에 맞춰 다음 대사와 선택지 3개 생성. 한 턴에 새 위험 신호는 최대 1개 |
| 상황 변형 | Gemini | 위험 신호는 그대로 두고 앱·말투·맥락만 바꾼 새 상황 |
| 정상 상황 생성 | Gemini | 위험 신호가 없는 상황 변형. 위험 요구가 섞이지 않았는지 검사 |
| 위험 신호 판별 | 규칙 (모델 안 씀) | 아이가 고른 선택지 기록으로 신호마다 찾음 / 놓침 / 안 나옴 판정 |
| 피드백 | Gemini | 판별 결과를 쉬운 말 피드백 카드로 |
| 힌트 | 규칙 | 백엔드가 정한 단계(0~3)에 맞춘 준비된 힌트 |
| 보호자 요약 | Gemini | 백엔드가 계산한 학습 결과를 1~2문장으로. 숫자는 만들지 않음 |
| 안전 필터 | 규칙 | 자해·폭력 피해 표현 시 연습 중단, 개인정보 가림, 위험한 출력 차단 |

- 모든 모델 출력은 규칙으로 다시 검사하고, 통과하지 못하면 준비된 문장으로 이어 갑니다.
- 위험 신호 **판별**(찾음/놓침)은 AI 서버가 하고, 그 결과로 **점수**를 계산하는 일은 백엔드가 합니다.
- 판단 이유 분석(아이가 직접 쓴 이유에 피드백)은 2차(P2) 범위로 API만 만들어 두었습니다.

## 3. AI 처리 흐름

### API 호출 순서

```
백엔드 ── variant  ──▶ AI 서버 : 상황 변형 / 정상 상황 생성 (필요할 때, 연습 전에)
백엔드 ── start    ──▶ AI 서버 : 첫 대사 + 선택지 3개
백엔드 ── turn     ──▶ AI 서버 : 다음 대사 + 선택지 (반복, 종료는 백엔드가 판단)
백엔드 ── judge    ──▶ AI 서버 : 위험 신호별 판별 결과
백엔드 ── feedback ──▶ AI 서버 : 쉬운 말 피드백
백엔드 ── summary  ──▶ AI 서버 : 보호자용 학습 요약 (리포트를 열 때)
```

### 요청 하나가 처리되는 과정

```
백엔드 요청
 → ① 인증 확인 (X-Internal-Token) · 입력 형식 검증 (실패 시 401 / 422)
 → ② 아이 글 안전 확인: 개인정보 가림 / 자해·폭력 피해 표현이면 모델을 부르지 않고 연습 중단 안내
 → ③ AI 모델 호출
 → ④ 출력 검사: 안전 필터 + 콘텐츠 규칙 (새 위험 신호 1개 이하, 선택지 형식, 정상 상황 속 위험 요구 등)
 → ⑤ 통과하면 결과 반환 / 실패하면 1번 다시 생성, 그래도 실패하면 준비된 대체 문장 반환
 → 백엔드로 응답 (source 필드로 model / fallback 구분)
```

AI 서버는 대화 기록을 따로 저장하지 않습니다. 대화 기록과 드러난 위험 신호는 백엔드가 저장해서 매번 요청에 담아 보냅니다.

## 4. 설치 및 실행

Python 3.11 이상이 필요합니다.

```bash
pip install -r requirements.txt
cp .env.example .env      # .env 는 커밋하지 않기
```

`.env`를 열어 값을 채웁니다. `AI_INTERNAL_TOKEN`은 꼭 넣어야 하고, 모델을 쓰려면 `AI_PROVIDER=gemini`와 `GEMINI_API_KEY`가 필요합니다. 키 없이 확인만 할 때는 `AI_PROVIDER=fake`로 두면 모델 없이 고정 답으로 동작합니다.

| `.env` 항목 | 뜻 |
|---|---|
| `AI_INTERNAL_TOKEN` | 백엔드가 보내는 인증 토큰 (없으면 서버가 뜨지 않음) |
| `AI_PROVIDER` | `fake`: 모델 없이 고정 답(테스트용) / `gemini`: Gemini 사용 (API 키 필요) |
| `GEMINI_API_KEY` · `GEMINI_MODEL` | Gemini 키(`gemini`일 때 필수) · 모델 이름 (기본 `gemini-2.5-flash`) |
| `AI_PORT` · `AI_HOST` | 포트와 주소 (기본 `8081` · `127.0.0.1`) |

```bash
make run                  # 또는 python -m app  →  http://127.0.0.1:8081
curl http://127.0.0.1:8081/health
```

## 5. API 명세

**인증:** `/health`를 뺀 모든 요청은 `X-Internal-Token` 헤더가 `.env`의 `AI_INTERNAL_TOKEN`과 같아야 합니다.
**형식:** 요청·응답 모두 JSON(`Content-Type: application/json`, UTF-8), 요청 본문은 64KB 이하입니다.

| 경로 | 설명 | 요청 / 응답 샘플 |
|---|---|---|
| `GET /health` | 상태 확인 (인증 없음) | — |
| `POST /internal/v1/practice/start` | 첫 대사 + 선택지 | `contracts/practice.start.*.json` |
| `POST /internal/v1/practice/turn` | 다음 대사 + 선택지 | `contracts/practice.turn.*.json` |
| `POST /internal/v1/practice/variant` | 상황 변형 / 정상 상황 생성 | `contracts/practice.variant.*.json`, `practice.normal.variant.*.json` |
| `POST /internal/v1/practice/judge` | 위험 신호 판별 | `contracts/practice.judge.*.json` |
| `POST /internal/v1/practice/feedback` | 피드백 | `contracts/practice.feedback.*.json` |
| `POST /internal/v1/summary` | 보호자 요약 | `contracts/summary.*.json` |

**주요 오류**

| 상태 | `error` | 뜻과 처리 |
|---|---|---|
| 400 | `invalid_json` | 본문이 JSON이 아님 |
| 401 | `unauthorized` | 토큰이 없거나 틀림 |
| 404 | `scenario_not_found` | 없는 시나리오 id |
| 413 | `payload_too_large` | 본문이 64KB 초과 |
| 422 | `invalid_request` | 입력 형식 오류. `fields`에 틀린 필드 **이름만** 담음 (입력 값은 담지 않음) |
| 422 | `invalid_variant` | 보낸 변형이 원래 시나리오의 틀(위험 신호 순서 등)과 맞지 않음 |
| 500 | `internal_error` | 서버 오류. 로그에는 오류 종류만 남김 |

모델이 실패해도 오류를 내지 않고 **200 + 준비된 문장**(`source: fallback`)으로 응답합니다. 보호자 요약만 실패 시 `{"summary": null}`을 돌려주며, 백엔드는 요약 칸을 비웁니다.

선택지 전달 방법, 힌트 단계, 정상 상황 처리 등 백엔드 연동 규칙 전체는 **[docs/API_CONTRACT.md](docs/API_CONTRACT.md)**에 있습니다.

## 6. 기능별 요청 예시

서버를 켠 뒤 `contracts/`의 샘플 요청을 그대로 보냅니다. 응답 형식은 같은 이름의 `*.response.json`과 같습니다. 다만 `AI_PROVIDER=fake`로 켜면 모델 대신 준비된 문장(`source: fallback`)이 나오므로 문장 내용은 샘플과 다를 수 있습니다.

```bash
TOKEN=change-me   # .env 의 AI_INTERNAL_TOKEN
ai() { curl -s -X POST "http://127.0.0.1:8081$1" -H "Content-Type: application/json" -H "X-Internal-Token: $TOKEN" -d @"$2"; echo; }

ai /internal/v1/practice/start    contracts/practice.start.request.json     # 첫 대화 시작
ai /internal/v1/practice/turn     contracts/practice.turn.request.json      # 다음 대화 생성
ai /internal/v1/practice/variant  contracts/practice.variant.request.json   # 상황 변형
ai /internal/v1/practice/judge    contracts/practice.judge.request.json     # 위험 신호 판별
ai /internal/v1/practice/feedback contracts/practice.feedback.request.json  # 피드백 생성
ai /internal/v1/summary           contracts/summary.request.json            # 보호자 학습 요약
```

예: 보호자 학습 요약 (`contracts/summary.*.json`)

```jsonc
// 요청
{"area": "친구의 무리한 부탁", "practice_count": 3, "found_clues": ["압박하는 말투"], "missed_clues": ["돈 요구"], "growth_level": null}
// 응답
{"summary": "부탁이 무리한지 생각해 보는 모습이 좋아요. 거절하는 연습을 해 보면 좋겠어요."}
```

켜진 서버에 모든 기능을 한 번에 보내 보려면 `python scripts/check_server.py`를 실행합니다.

## 7. 콘텐츠 구성

| 영역 | 위험 상황 | 정상 상황 | 예시 |
|---|---|---|---|
| 사기 | 4 | 8 | SNS 고수익 알바, 게임 아이템 거래, 용돈 이벤트 |
| 명의 빌려주기 | 4 | 8 | 통장·체크카드 빌려주기 알바, 선배의 휴대폰 개통 부탁 |
| 친구의 무리한 부탁 | 4 | 8 | 숙제 대신 해 주기, 용돈 빌려 달라고 조르기 |

- 위험 신호 12개는 금융감독원·금융위원회·고용노동부 등 **공공기관 자료를 근거**로 만들었습니다.
- 진단 3문항(영역마다 1문항)이 함께 있습니다.
- 시나리오 목록, 플랫폼 ID, 단서별 출처, 시나리오 추가 규칙은 **[docs/CONTENT_GUIDE.md](docs/CONTENT_GUIDE.md)**에 있습니다.

## 8. 기술 스택과 AI 제공자

| 기술 | 선택 이유 |
|---|---|
| Python 3.11 | AI 기능 구현과 API 연동에 적합하며, Gemini 공식 SDK 지원 |
| Gemini `gemini-2.5-flash` (`google-genai`) | 개발 단계 모델. 한국어 대화가 자연스럽고 응답이 빠름 |
| 표준 라이브러리 HTTP 서버 | 백엔드만 부르는 내부 서버라 프레임워크 없이 가볍게 |
| `pydantic` | 요청·응답 검증 |
| `pytest` + GitHub Actions | push·PR마다 자동 테스트 |

### AI 제공자 정책 검토

SLOW:RE의 핵심 이용자는 중·고등학생 연령대의 청소년입니다. 그래서 정식 서비스에 쓸 AI 제공자는 **미성년자 대상 서비스 이용 조건**을 먼저 확인해야 합니다.

- **Gemini API:** [Gemini API 추가 이용약관](https://ai.google.dev/terms)은 18세 미만이 대상이거나 이용할 가능성이 높은 웹사이트·앱·서비스의 일부로 API를 쓰지 못하게 합니다. 이 조건은 유료 결제 여부와 관계없이 적용되므로, 결제만으로 이 제한이 풀리지 않습니다.
- **Claude API (우선 검토):** Anthropic은 [미성년자 대상 서비스를 만드는 조직을 위한 가이드](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors)를 따로 공개하고 있습니다. 이 가이드는 연령 확인, 콘텐츠 필터링, 모니터링·신고 체계, 안전한 사용 교육 자료, AI와 대화 중이라는 사실의 고지, 아동 안전·개인정보 법규 준수 등을 요구합니다. 미성년자 대상 서비스를 조건부로 허용하는 기준이 공개되어 있어 우선 검토 대상으로 정했습니다. **이 조건을 충족해야 쓸 수 있으며, 무조건 사용할 수 있는 것은 아닙니다.**

**현재 개발 단계**
- 이미 결제한 Gemini API는 개발과 비교 테스트에만 쓰고, 실제 미성년자 이용자와는 연결하지 않습니다.
- 테스트에는 실제 아이의 글이 아닌 합성 데이터와 개발용 시나리오만 씁니다.
- 개발 단계의 이 사용이 약관 범위에 드는지는 팀에서 약관 원문으로 다시 확인합니다.

**정식 서비스 전 (예정)**
- 미성년자 대상 서비스 이용 조건과 데이터 보호 정책을 충족하는 AI 제공자를 선정합니다. Claude API를 우선 검토하지만 **아직 확정하지 않았습니다.**
- 선정 전에 제공자의 이용 조건과 데이터 처리·보관 정책, 국내 개인정보 보호법과 아동·청소년 관련 법률을 검토합니다.
- 연령 확인, 모니터링, AI 사용 고지처럼 제공자 가이드가 요구하지만 아직 없는 기능은 백엔드·프론트엔드와 함께 준비합니다.

### 제공자 교체 구조

| 구분 | 상태 |
|---|---|
| 모든 기능이 `LLMProvider` 인터페이스(`generate(prompt, json_mode)`) 하나로만 모델을 부름 | **구현됨** |
| 모델 SDK(`google-genai`)는 `app/providers.py` 한 파일에서만 import | **구현됨** |
| 모델 없이 동작하는 `FakeProvider` (테스트·CI·키 없는 로컬 실행용) | **구현됨** |
| 백엔드와의 API 계약(`contracts/`)은 제공자와 무관하게 동일 | **구현됨** |
| Claude용 Provider 추가와 `AI_PROVIDER=claude` 설정 | **예정** (미구현) |
| 새 제공자에 맞춘 프롬프트·JSON 출력 방식 조정과 출력 품질 비교 | **예정** |

대화 생성, 상황 변형, 피드백 같은 기능 코드는 Provider만 부르므로, 제공자를 바꿀 때는 Provider 계층과 설정을 추가하는 것이 주된 작업입니다. 다만 모델마다 출력 경향이 달라 프롬프트 조정과 품질 확인은 따로 필요합니다.

## 9. 폴더 구조

```
app/          서버와 기능 코드 (practice: 대화, variation: 변형, judge: 판별·피드백, safety: 안전 필터 …)
content/      연습 콘텐츠 JSON (위험 신호, 시나리오, 진단 문항, 안전 문구)
contracts/    백엔드와 맞춘 요청·응답 샘플
docs/         API 연동 명세, 콘텐츠 가이드
scripts/      켜진 서버로 기능별 요청을 보내 보는 확인 도구
tests/        pytest
```

## 10. 테스트

```bash
make test                         # 전체 테스트 (모델 안 씀, FakeProvider)
python scripts/check_server.py    # 켜진 서버에 기능별로 실제 요청을 보내 확인
```

- push·PR마다 GitHub Actions가 전체 테스트를 돌립니다(위 배지).
- 실제 모델이 낸 잘못된 출력은 회귀 테스트로 남깁니다(`tests/test_normal_regression.py`).
- 콘텐츠 규칙(단서가 대사에 있는지, 대사가 안전한지 등)도 테스트로 확인합니다.

## 11. 안전 및 개인정보

이용자가 미성년자이므로 다음을 지킵니다.

**구현된 것**
- **AI 서버 자체 저장 없음:** AI 서버는 대화 기록과 학습 데이터를 저장하지 않습니다. 대화 기록은 백엔드가 관리하고 요청마다 보내 줍니다.
- **로그 최소화:** 운영 로그에는 `메서드 경로 -> 상태코드`만 남깁니다. 요청 본문, 프롬프트, 모델 출력은 남기지 않고, 오류도 종류만 남깁니다.
- **개인정보 사전 가림:** 주민번호·전화번호·계좌번호·주소·학교 이름은 모델에 보내기 전에 가립니다.
- **위험 표현 시 연습 중단:** 자해·폭력 피해 표현이 나오면 모델을 부르지 않고 연습을 멈춘 뒤, 믿는 어른과 상담 전화(109, 1388, 117, 112)를 안내합니다(`status: safe_reply`).
- **출력 검증과 차단:** 진짜 같은 링크·번호, 사기 방법 설명, 비난·진단명·점수 표현, 정상 상황 속 개인정보·금전 요구를 막고, 걸리면 다시 만들거나 준비된 문장을 씁니다.
- **API 키 관리:** 모델 API 키는 `.env`에만 두고 저장소에 올리지 않습니다.

**외부 AI 제공자의 데이터 처리**

AI 서버가 저장하지 않더라도, 모델을 부르면 (가린 뒤의) 요청 내용이 외부 제공자에게 전달됩니다. 제공자 쪽의 기록·보관·학습 사용 여부는 **각 제공자의 약관과 실제 계약 조건**을 따릅니다. 예를 들어 Gemini API 약관은 무료 서비스에서는 입력과 출력을 제품 개선에 쓰고 사람이 검토할 수 있다고, 유료 서비스에서는 제품 개선에 쓰지 않되 정책 위반 감지를 위해 일정 기간 기록한다고 밝히고 있습니다.

**앞으로 검토할 것**
- 정식 서비스 제공자의 데이터 보관·학습 정책 확인 ([8장](#ai-제공자-정책-검토))
- 연령 확인, 사용 모니터링, AI 사용 고지 (백엔드·프론트엔드와 함께)
- 국내 개인정보 보호법, 아동·청소년 관련 법률 검토

## 12. 팀 및 참고 자료

- **팀:** 1호선톤 15조 ([line1thon-15](https://github.com/line1thon-15)). 이 저장소는 AI 파트이고, 백엔드·프론트엔드는 각 저장소에 있습니다.
- **콘텐츠 근거:** 금융감독원, 금융위원회, 고용노동부, 교육부 등 공공기관 자료 ([출처 목록](docs/CONTENT_GUIDE.md#단서-출처))
- **AI 제공자 정책:** [Gemini API 추가 이용약관](https://ai.google.dev/terms), [Anthropic: 미성년자 대상 서비스 조직을 위한 가이드](https://support.claude.com/en/articles/9307344-responsible-use-of-anthropic-s-models-guidelines-for-organizations-serving-minors)
- **라이선스:** 팀과 협의해서 정할 예정입니다.
