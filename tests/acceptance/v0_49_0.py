"""v0.49.0 배포 전 LIVE acceptance spec — rnd_info_processing manifest 현행화.

읽는 법(비프로그래머용): 이번 릴리스는 데이터-only입니다 — 「국가연구개발정보처리기준」의
등록 스냅샷 2값(api_doc_id 2100000195842 → 2100000283100·effective_date 2021-01-01 →
2026-08-20)만 바뀌고 코드 실행 경로 변경이 없습니다(contract 0.34.0 유지·재연결 불요).
Level A의 표적은 ①신판 문서가 LIVE에서 실제 도달·정확한가(폴백 ID 실도달성 증명)
②광역 fan-out 무회귀 두 가지입니다.

★실행 시점 전제(§5.40 — 실 assert로 구현·diff 적대검토 Codex 2라운드 반영): 본 spec은
2026-08-20 시행 도래 후 실행을 전제합니다. 시행일 게이트 = 문서레벨 체크의 WARN 4종 —
①effective_date == "2026-08-20"(신판 식별 증거 — 구조 지표[조문 25 등]는 구판과 동일해
식별 증거가 아님) ②revision_notice == "<missing>"(스냅샷=현행 일치 시 미발화 — 역방향
발화 검출) ③resolve_fallback_notice == "<missing>"(resolve 실패 폴백은 manifest 신값을
그대로 돌려줘 ①②가 헛통과하는 우회 경로 — 이 고지 발화로 검출) ④upcoming_revision ==
"<missing>"(시행 전 정상 resolve·미래행-only 폴백 모두 이 고지가 발화해 검출). 시행 전
오실행·resolve 이상은 이 4종 중 최소 1개가 어긋나 드러납니다 — 서버 회귀가 아니라 실행
시점·환경 신호이므로 날짜 확인 후 08-20 이후 재실행하십시오. 아울러 resolve 캐시
(86,400s) 오염을 피하기 위해 러너는 새 프로세스(fresh client)로 실행해야 합니다
(run.py 1회 구동 = 새 프로세스라 기본 충족).

★사람 판정 참고: BP0000(별표 0000)은 신판에서 본문 178,275자(구판 39,259자의 약
4.5배)로 확대되었습니다. oversized_pointer·annex_chunk는 기존 경로가 처리하므로
content_format 확인은 WARN 참고용이며, 이 체크의 latency 초과는 대형 데이터 유래일 수
있어 차단하지 않습니다(false-block-safe).

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out 대형 규정 도달 + recall(릴리스 간 동일 문안)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — 대량이면 infra 여부 사람 판정
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "표적 — 검색 fan-out에서 rnd_info_processing 도달(신판 자동 선택 경로)",
        "tool": "search_provision",
        "args": {"query": "연구개발정보 등록"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_info_processing"},                 # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 1},                                   # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN — 178k 별표 유래 지연 감시
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
    {
        "name": "표적 — 신판 문서레벨 상세 직접 도달(폴백 ID 실도달성·신판 식별·시행일 게이트)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000283100"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 신 ID 오타·미존재 검출
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "articles_count", "value": 25},              # WARN — 사전 실측(2026-08-13) 구조 잠금(구판 동일 — 식별 증거 아님)
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN — ★신판 식별 증거 + 시행일 게이트(시행 전 오실행 검출)
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN — ★스냅샷=현행 일치로 미발화 정상(역방향 발화 검출)
            {"kind": "field_equals", "path": "resolve_fallback_notice", "value": "<missing>"},  # WARN — ★폴백 우회 차단(재검증 라운드 Codex — resolve 실패 폴백은 manifest 신값을 그대로 돌려줘 위 2개가 헛통과)
            {"kind": "field_equals", "path": "upcoming_revision", "value": "<missing>"},  # WARN — ★미래행-only 우회 차단(시행 전 정상 resolve·미래행 폴백 모두 이 고지가 발화해 검출)
        ],
    },
    {
        "name": "표적 — 신판 JO 상세 verbatim(제1조·평면 schema 파서 무회귀)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000283100:JO0001"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "표적 — BP0000 대형 별표(178,275자) 기본 조회(oversized_pointer 강등 확인)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000283100:BP0000"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "annex_unavailable_parse_failed"},     # WARN — 대형 별표 파싱 실패 검출
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — ★178k는 예산 초과 = 포인터 강등이 정상(전문 수록이면 예산 회귀 의심)
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 대형 데이터 기록용
        ],
    },
    {
        "name": "표적 — BP0000 annex_chunk=1 청크 조회(대형 별표 분할 경로 실동작)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000283100:BP0000", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 청크 범위·ID 정상
            {"kind": "absent_error_code", "value": "annex_unavailable_parse_failed"},     # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 본문은 원문 그대로
            {"kind": "field_equals", "path": "chunk_index", "value": 1},                  # WARN — 요청 청크 반환 확인
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). 표적 = 호스트가 신판 기준으로 정확히
# 안내하는가(개정 반영·시행일)·광역 무회귀. 무회귀 문안은 v0.48.0 spec verbatim 재사용
# (릴리스 간 A/B 비교 기준 유지 — [[eval-probe-design-standard]]).
LEVEL_B_PROMPTS = [
    {
        "category": "표적 A — 신판 도달·개정 인지(신규 문안·차기 릴리스부터 verbatim 재사용)",
        "probe_prompt": "국가연구개발사업에서 과제 정보와 연구자 정보, 성과 정보는 어디에 어떻게 "
                        "등록해야 하는지 규정 근거와 함께 알려줘. 이 기준이 최근 개정되었는지, "
                        "지금 시행 중인 판은 언제부터 시행된 것인지도 확인해줘.",
        "expect_behavior": "rnd_info_processing 도달 + 2026-08-20 시행 개정본 기준 답변·조문 인용. "
                           "구판(2021-01-01)을 현행으로 안내하거나, 개정 여부를 반대로 안내하면 실패. "
                           "revision_notice 부재(스냅샷=현행 일치로 미발화)가 정상.",
    },
    {
        "category": "무회귀 B — cold 광역 fan-out 경로(v0.48.0 무회귀 B verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out 완주·기존 규정(연구개발비 사용 기준·시행령) 중심 유지 + "
                           "citation·footer 무회귀. 부분 timeout·누락 규정·오류 문면이 새로 보이면 "
                           "회귀 의심(178k 별표 유래 지연 여부 분리 확인).",
    },
]
