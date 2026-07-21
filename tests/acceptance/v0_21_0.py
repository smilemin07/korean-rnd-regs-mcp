"""v0.21.0 배포 전 LIVE acceptance spec — 「대용량 별표 내 검색(annex_locate) opt-in」.

읽는 법(비프로그래머용): 이번 v0.21.0은 get_provision_detail에 optional 입력 annex_locate를 추가해,
대용량(oversized) 별표의 전문 텍스트를 서버가 줄 단위로 스캔한 결과(annex_locate_result)를 반환합니다.
Level A(자동)는 ① 신기능 결정론 확인(locate 블록 실반환·0매치 앵커 total_match_count=0) ② 무회귀
(기본 경로 oversized_pointer 유지·검색 fan-out recall)를 확인합니다. 개선의 소비 품질(호스트가 청크
전수 순회 대신 locate를 먼저 쓰는지·부재 결론에 한계를 표시하는지)은 호스트 LLM 행동(Level B)이라
배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★locate·별표 관련 항목은 전부 WARN 클래스 — 별표가 개정으로 예산 내 크기로 줄면 locate가 무시(전문
  수록)로 바뀌는 것이 정상 거동이고, 매치 수·부재는 LIVE 데이터 개정에 따라 변할 수 있어 hard-BLOCK
  부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "개선 A — law 대용량 별표 locate 실반환(law:285767:BP0002 annex_locate='인건비' → 전문 스캔 블록)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_locate": "인건비"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 포인터 유지(additive)
            {"kind": "field_equals", "path": "annex_locate_result.scanned_scope", "value": "annex_full_text"},  # WARN — 전문 스캔 앵커
        ],
    },
    {
        "name": "개선 B — 0매치 결정론 앵커(law:285767:BP0002 annex_locate='존재하지않는문구XYZ' → total_match_count=0)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_locate": "존재하지않는문구XYZ"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "annex_locate_result.total_match_count", "value": 0},  # WARN — 미발견 앵커
        ],
    },
    {
        "name": "개선 C — admrul 경로 locate(평가관리지침 admrul:2100000252016:BP0001 'RCMS' → 0매치·eval GT 재현)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000252016:BP0001", "annex_locate": "RCMS"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "annex_locate_result.total_match_count", "value": 0},  # WARN — v0.20.x eval GT(개정 시 변동 가능)
        ],
    },
    {
        "name": "무회귀 A — 기본 경로 무변(law:285767:BP0002 annex_locate 미지정 → oversized_pointer·locate 필드 없음)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 B — 청크 조회 유지(law:285767:BP0002 annex_chunk=1 → verbatim 청크·v0.20.0 기능 무회귀)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 유지
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타 유지
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(locate 추가가 검색 경로 무해)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 실측 ~16-17·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.21.0 = 부재 확인의 1-call 라우팅이 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★locate 라우팅 — 부재 확인을 청크 전수 순회 대신 annex_locate로",
        "probe_prompt": "산업기술혁신사업 기술개발 평가관리지침 별표들에 RCMS라는 용어가 나오는지 확인해줘.",
        "expect_behavior": "v0.20.0/v0.20.1 eval P2 재실행 — 청크 7회 전수 순회 대신 annex_locate를 먼저 사용해 "
                           "1~3회 호출로 부재를 확정하는지 + '서버가 별표 전문을 스캔한 결과'(scanned_scope) 근거와 "
                           "스캔 한계(줄 단위·HWP 첨부 제외)를 함께 표시하는지 확인.",
    },
    {
        "category": "★locate 매치 소비 — 존재 확인 + chunk_index로 해당 구간만 후속 조회",
        "probe_prompt": "국가연구개발혁신법 시행령 별표 2에서 인건비 관련 항목이 어디에 나오는지 찾아서 "
                        "해당 부분 원문을 보여줘.",
        "expect_behavior": "annex_locate로 매치 위치를 찾고, 전수 순회 없이 매치의 chunk_index에 해당하는 "
                           "annex_chunk만 조회해 원문을 인용하는지 + excerpt(부분 발췌)를 별표 전체로 "
                           "오인하지 않는지 확인.",
    },
    {
        "category": "★과확장 방지 — 0매치 결론의 범위 한정",
        "probe_prompt": "산업기술혁신사업 공통 운영요령이랑 평가관리지침 어디에도 RCMS 언급이 없는 게 맞아?",
        "expect_behavior": "locate 0매치를 '해당 별표 전문 텍스트에서 미발견'으로 한정 표시하는지 — 문서 전체·"
                           "HWP 첨부·미조회 별표까지 부재로 과확장 단정하지 않는지 + 확인 범위(어느 별표를 "
                           "스캔했는지)를 명시하는지 확인.",
    },
    {
        "category": "무회귀 — 기존 청크·amendment 지시와의 상호 간섭 없음",
        "probe_prompt": "중소기업 기술혁신 촉진법이 최근 개정으로 뭐가 바뀌었는지 빠짐없이 알려줘",
        "expect_behavior": "v0.17.1~v0.20.1 검증 시나리오 재실행 — locate 지시 삽입 후에도 amendment_text 개정 "
                           "지시 항목을 가지조문 포함 전수 열거하고 근거 법률 인용을 보존하는지(기존 지시 희석 없음).",
    },
]
