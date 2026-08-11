"""v0.48.0 배포 전 LIVE acceptance spec — fan-out 안정화(B3 LIVE HTTP 연결 재사용).

읽는 법(비프로그래머용): 이번 릴리스는 transport-only입니다 — 모든 LIVE 호출의 단일
관문(live_api._request_with_retry)이 bare requests.get 대신 스레드-로컬 keep-alive
Session(_http_get seam)을 재사용합니다. 응답 필드·오류 코드·입력 스키마·규정 데이터는
전부 무변이므로(contract 0.34.0 유지·재연결 불요), Level A의 표적은 "새 전송 경로가
LIVE에서 기존과 동일하게 동작하는가"(무회귀)입니다. 설계 불변식 자체(세션 재사용·격리·
쿠키 비움·폐기·폴백)는 결정론 단위테스트(tests/test_b3_session.py)가 전담하고, 여기서는
새 전송 경로로 실제 law.go.kr을 때리는 대표 4경로(광역 fan-out·admrul JO 상세·law JO
상세·law 문서레벨 old_and_new opt-in)를 검증합니다.

★cold latency는 기록만 합니다(latency_under는 WARN) — B3의 절감 폭(호출당 약 105ms
실측·2026-08-11)은 네트워크 변동에 묻힐 수 있고, latency로 자동 BLOCK하지 않는 것이
기존 false-block-safe 규율입니다. 회귀 신호는 fetched_ok·returned_not_below(기능 무회귀)
2종뿐입니다.

★사람 판정 승격 규약(diff 적대검토 Codex MINOR 반영 — 러너는 WARN으로 출력하나 배포
게이트에서 사람이 승격 판단할 것): 이 릴리스는 전송 계층 자체를 바꾸므로, 평시에는
"전건/과반 parse_failed = 상위 API 장애(infra)"로 분류하던 대량 오류가 이번에는 B3 회귀
(Session 경로의 광역 연결 실패)일 수 있습니다. 검색 체크의 parse_failed WARN이 다수
관측되면 상위 API 장애로 단정하지 말고, 직전 v0.47.0 코드(예: git stash 또는 태그
체크아웃)로 동일 질의를 교차 재현해 원인을 분리한 뒤에만 배포를 진행하십시오 —
v0.47.0에서만 정상이면 B3 회귀 = 배포 보류.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out(신 전송 경로) 대형 규정 도달 + recall",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — 대량이면 사람 판정 승격(위 규약)
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용(B3 전후 비교)
        ],
    },
    {
        "name": "무회귀 — v0.47.0 신규 규정 검색 도달 유지('사업계획검토'·릴리스 간 동일 문안)",
        "tool": "search_provision",
        "args": {"query": "사업계획검토"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "large_rnd_plan_review"},               # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 1},                                   # 회귀=BLOCK 후보
            {"kind": "field_equals", "path": "results.0.rule_set_id",
             "value": "large_rnd_plan_review"},                                           # WARN
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — 대량이면 사람 판정 승격(위 규약)
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
    {
        "name": "무회귀 — admrul JO 상세 verbatim(신 전송 경로·v0.47.0 동일 표적)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000276390:JO0008"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "title", "value": "사업계획검토 수행기관"},   # WARN
        ],
    },
    {
        "name": "무회귀 — law JO 상세(중기법 제10조·latest_history 보유 조문·신 전송 경로)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987:JO0010"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — law 문서레벨 + include_old_and_new opt-in(별도 상위 endpoint 전송 경로)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987", "include_old_and_new": True},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "old_and_new.available", "value": True},     # WARN — opt-in 실호출 성공 실증(2026-08-11 실측 True·fetch_failed면 False로 드러남)
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.48.0은 transport-only라 호스트 가시 변화가
# 0 — Level B의 표적은 "실제 호스트 경로(웹 커넥터→NAS→law.go.kr)에서 신 전송 계층이
# 기존과 동일하게 규정 도구를 완주시키는가"(무회귀)다. 문안은 v0.47.0 spec verbatim 재사용
# (릴리스 간 A/B 비교 기준 유지 — [[eval-probe-design-standard]]). 판정: 도구 오류·부분
# timeout 없이 기존과 같은 조문 도달·인용·footer면 PASS. 호스트가 도구를 아예 안 불렀으면
# B3 실패가 아니라 'eval 무효'로 분류(문안 보강 후 재실행).
LEVEL_B_PROMPTS = [
    {
        "category": "무회귀 A — 신규 고시 상세 조회 경로(v0.47.0 표적 A verbatim)",
        "probe_prompt": "대형 연구개발사업의 사업계획검토는 어떤 절차로 진행되고, 검토를 "
                        "수행하는 기관과 점검항목은 무엇인지 규정 근거와 함께 알려줘.",
        "expect_behavior": "large_rnd_plan_review 도달 + 제8조·제11조 등 조문 인용·별지 미노출 "
                           "정직 고지 — v0.47.0 eval과 동일 수준이면 무회귀 PASS. 도구 오류·"
                           "timeout·규정 미도달이 새로 생기면 전송 계층 회귀 의심(3단계 분류).",
    },
    {
        "category": "무회귀 B — cold 광역 fan-out 경로(v0.47.0 음성 대조 verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out(신 전송 경로)이 완주하고 기존 규정(연구개발비 사용 "
                           "기준·시행령)이 답변 중심 유지 + citation·footer 무회귀. 부분 "
                           "timeout·누락 규정·오류 문면이 새로 보이면 회귀 의심.",
    },
    {
        "category": "무회귀 C — 부칙 적용례 정확성(v0.47.0 표적 B verbatim)",
        "probe_prompt": "구축형 연구개발사업의 사업추진심사는 언제 어떻게 요구해야 하는지 "
                        "알려줘. 이 지침이 지금 시행 중인지도 확인해줘.",
        "expect_behavior": "build_type_rnd_screening 도달·제17조 인용·2026-05-11 시행 중 + 부칙 "
                           "제2조 적용례 구분 유지(v0.47.0 P2와 동일 수준). known_limitations "
                           "소비 무회귀 확인.",
    },
]
