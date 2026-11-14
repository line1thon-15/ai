# 콘텐츠 가이드

연습 콘텐츠는 모두 `content/`의 JSON입니다. 코드를 바꾸지 않고 시나리오를 추가·수정할 수 있고, 규칙을 어기면 테스트가 실패합니다.

| 파일 | 내용 |
|---|---|
| `clues.json` | 위험 신호(단서) 12개: 이름, 뜻, 찾았다고 보는 기준, 안전한 대처, 힌트, 아이 말의 신호(`triggers`), 선택지 예시, 출처 |
| `scenarios/*.json` | 영역별 위험 상황 4개 + 정상 상황 8개 |
| `diagnosis.json` | 처음 설정의 진단 3문항 (자기 평가, 정답 없음). 백엔드 형식 `{id, text, options:[{id, text, score}]}`, 그래요 0 / 가끔 1 / 아니에요 2(점수가 높을수록 안전한 편, 합계 0~6). 피그마 Y2-1 문구 그대로. 합계 → 시작 난이도는 백엔드. 백엔드가 모르는 필드를 거부하므로 `version`, `questions` 외 필드는 넣지 않음 |
| `safety_cases.json` · `safety_messages.json` | 안전 필터 기준 사례 · 안내 문구와 상담 전화번호 |

## 시나리오 목록

| 영역 | 위험 상황 id | 난이도 | 기본 플랫폼 | 단서 (드러나는 순서) | 짝이 되는 정상 상황 |
|---|---|---|---|---|---|
| 사기 | `scam_dm_parttime_01` SNS로 온 쉬운 알바 제안 | 1 | `sns_dm` | too_good_pay, advance_payment, urgency, keep_secret | `normal_cafe_01`, `normal_center_01` |
| 사기 | `scam_jobboard_link_01` 채용 공고에서 시작된 링크 알바 | 2 | `open_chat` | suspicious_link, personal_info, urgency, keep_secret | `normal_board_01`, `normal_contract_01` |
| 사기 | `scam_game_item_01` 게임에서 만난 아이템 판매자 | 1 | `game_chat` | urgency, advance_payment, suspicious_link, personal_info | `normal_game_market_01`, `normal_game_support_01` |
| 사기 | `scam_allowance_event_01` SNS 용돈 이벤트 당첨 메시지 | 1 | `sns_dm` | too_good_pay, advance_payment, personal_info, keep_secret | `normal_allowance_family_01`, `normal_school_prize_01` |
| 명의 빌려주기 | `identity_dm_account_01` SNS로 온 통장 빌려주기 알바 | 1 | `sns_dm` | too_good_pay, lend_identity, no_risk_claim, urgency | `normal_bank_account_01`, `normal_pay_account_01` |
| 명의 빌려주기 | `identity_phone_senior_01` 선배가 부탁한 휴대폰 만들기 | 1 | `text_message` | lend_identity, too_good_pay, no_risk_claim, keep_secret | `normal_phone_store_01`, `normal_club_senior_01` |
| 명의 빌려주기 | `identity_openchat_card_01` 오픈채팅방의 체크카드 보내기 알바 | 2 | `open_chat` | lend_identity, too_good_pay, urgency, keep_secret | `normal_youth_labor_01`, `normal_bakery_job_01` |
| 명의 빌려주기 | `identity_game_account_01` 게임 친구가 부탁한 통장 쓰기 | 1 | `game_chat` | lend_identity, no_risk_claim, urgency, keep_secret | `normal_game_gift_01`, `normal_allowance_dad_01` |
| 친구의 무리한 부탁 | `friend_homework_01` 숙제를 대신 해 달라는 친구 | 1 | `messenger` | burdensome_request, ignoring_no, guilt_pressure, friendship_threat | `normal_study_together_01`, `normal_birthday_invite_01` |
| 친구의 무리한 부탁 | `friend_money_01` 용돈을 빌려 달라고 조르는 친구 | 1 | `messenger` | burdensome_request, urgency, ignoring_no, keep_secret | `normal_snack_share_01`, `normal_park_ride_01` |
| 친구의 무리한 부탁 | `friend_game_skin_01` 게임 스킨을 사 달라는 친구 | 1 | `game_chat` | burdensome_request, guilt_pressure, friendship_threat, keep_secret | `normal_game_party_01`, `normal_birthday_gift_01` |
| 친구의 무리한 부탁 | `friend_cover_lie_01` 대신 출석 대답을 해 달라는 친구 | 2 | `messenger` | burdensome_request, keep_secret, urgency, friendship_threat | `normal_ask_homework_01`, `normal_tell_teacher_01` |

## 플랫폼 ID

백엔드가 앱 유형을 아래 ID로 바꿔 `variant`의 `platform`에 넣습니다. 시나리오마다 쓸 수 있는 플랫폼은 `variation_axes.platform`에 있습니다(목록에 없으면 422).

| ID | 뜻 | 쓸 수 있는 시나리오 |
|---|---|---|
| `sns_dm` | SNS 쪽지(DM) | friend_homework_01, friend_game_skin_01, friend_cover_lie_01, identity_dm_account_01, identity_phone_senior_01, identity_openchat_card_01, identity_game_account_01, scam_dm_parttime_01, scam_game_item_01, scam_allowance_event_01 |
| `open_chat` | 오픈채팅 | identity_dm_account_01, identity_openchat_card_01, identity_game_account_01, scam_dm_parttime_01, scam_jobboard_link_01, scam_game_item_01, scam_allowance_event_01 |
| `text_message` | 문자 메시지 | friend_homework_01, friend_money_01, friend_cover_lie_01, identity_dm_account_01, identity_phone_senior_01, scam_dm_parttime_01, scam_jobboard_link_01, scam_allowance_event_01 |
| `friend_intro` | 아는 사람의 소개 | identity_phone_senior_01, scam_dm_parttime_01 |
| `job_board` | 채용 사이트 공고 | identity_openchat_card_01, scam_jobboard_link_01 |
| `game_chat` | 게임 속 채팅(귓속말) | friend_money_01, friend_game_skin_01, identity_game_account_01, scam_game_item_01 |
| `school_notice` | 학교 알림장 | - |
| `messenger` | 메신저 대화(아는 친구) | friend_homework_01, friend_money_01, friend_game_skin_01, friend_cover_lie_01 |

## 단서 출처

단서마다 근거 자료(`sources`)가 있고, `source_type`으로 종류를 나눕니다.

| source_type | 뜻 | 예 |
|---|---|---|
| `official` | 공공기관이 직접 낸 원문 (보도자료·소비자경보·홍보 게시물·정부 정책 포털) | 금융감독원 소비자경보, 금융위원회 보도참고, 고용노동부 지청 공지 |
| `local_gov` | 지방자치단체 홍보물 | 강남구청 카드뉴스 |
| `press` | 언론 보도·기고 (기관 발표를 2차 인용) | 경향신문, 머니투데이, 한국경제 생글생글 |

- `strength`: `direct`(그 단서를 직접 말함) / `indirect`(관련은 있지만 단서 문구 자체는 없음)
- 사기 영역 단서 6개는 모두 공공기관 원문 직접 근거가 있습니다(테스트로 확인).

- `strength`: `direct`(그 단서를 직접 말함) / `indirect`(관련은 있지만 단서 문구 자체는 없음)
- 사기 영역 단서 6개는 모두 공공기관 원문 직접 근거가 있습니다(테스트로 확인). 목록 안에서는 공공기관 원문이 앞에 옵니다.
- 보완 필요: `no_risk_claim`(안심시키는 말)은 언론 보도만 있고, `guilt_pressure`(미안한 마음 들게 하기)는 출처가 없습니다.

## 시나리오를 추가할 때 지킬 것

테스트(`tests/test_scenarios.py`, `tests/test_normal*.py`)가 아래를 확인합니다.

- **단서 대사(`reveal_line`)에는 그 단서의 키워드가 있어야** 합니다. 대사가 단서를 실제로 드러내는지 키워드로 판단합니다.
- **뒤에 나올 단서의 키워드가 앞 대사에 섞이면 안 됩니다.** 한 턴에 새 단서는 최대 1개입니다.
- **첫 단서는 첫 대사에서 드러나야 합니다**(`at_opening: true`, 첫 대사에 그 단서의 키워드). 첫 선택지부터 아이가 단서에 반응할 수 있게 하기 위해서입니다.
- 단서의 선택지 예시가 상황과 어색하면 시나리오에 `opening_choices`(첫 단서에 맞춘 시작 선택지)를 넣을 수 있습니다. 모델 선택지와 같은 규칙(정답은 분명한 거절, 길이 비슷 등)을 지켜야 합니다.
- 영역마다 알바가 아닌 시나리오가 2개 이상 있어야 합니다(고수익 알바 상황은 고등학생에게만 맞기 때문).
- **정상 상황**에는 `keep`(꼭 남을 맥락·상대 관계), `signal_checks`(안심 신호 확인 단어), `fallback_line`(모델 실패 시 대사)을 넣고, 위험 요구 표현은 넣지 않습니다.
- 모든 대사는 안전 필터를 통과해야 합니다.
