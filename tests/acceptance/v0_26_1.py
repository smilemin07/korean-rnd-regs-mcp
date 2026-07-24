"""v0.26.1 배포 전 LIVE acceptance spec — 「별표 방식 라벨 실효 트리거 정밀화 — 완성형 라벨 예시 + 캡션 위치 고정」.

읽는 법(비프로그래머용): 이번 v0.26.1은 코드 로직·응답 schema 변경이 전혀 없는 프롬프트 문자열-only
patch입니다(v0.17.1·v0.19.1·v0.20.1·v0.21.1·v0.23.1·v0.24.1과 동형·7번째). 서버가 반환하는 데이터는
v0.26.0과 동일해야 하므로 Level A(자동)는 무회귀 확인만 수행합니다 — ① 자율주행 신규 1건 포함 검색
도달·별표 tier-1·기본 경로(oversized_pointer)·청크·amendment 부착이 그대로인지 ② 검색 fan-out recall이
유지되는지. 개선 자체(별표 방식 라벨을 표·목록의 캡션 또는 바로 앞·뒤 문장에 완성형 관용구로 표시)는
호스트 LLM 행동(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★별표·amendment 관련 항목은 전부 WARN 클래스 — 별표가 개정으로 크기·구성이 바뀌거나 amendment_kind가
  LIVE 개정에 따라 변하는 것은 정상 거동이라 hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음).
  BLOCK 후보는 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "무회귀 A — 자율주행 검색 도달 유지('자율주행' 무접두 fan-out — v0.26.0 신규 승계)",
        "tool": "search_provision",
        "args": {"query": "자율주행"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "kt_autonomous_driving"},                   # v0.26.0 신규 — 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
        ],
    },
    {
        "name": "무회귀 B — 자율주행 별표 3 tier-1 유지(admrul:2100000282292:BP0003 — v0.26.0 실측 승계)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282292:BP0003"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 유지
        ],
    },
    {
        "name": "무회귀 C — 자율주행 문서레벨 amendment 부착 유지(amendment_kind=타법개정 — v0.26.0 실측 승계)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282292"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "타법개정"},            # WARN — 2026-07-24 재프로브 실측(부처명 정비)
        ],
    },
    {
        "name": "무회귀 D — 기본 경로 무변(law:285767:BP0002 opt-in 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 E — 청크 조회 유지(law:285767:BP0002 annex_chunk=1 → verbatim 청크·v0.20.0 기능)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 유지
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타 유지
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(프롬프트 문자열 변경이 검색 경로 무해)",
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.26.1 = 라벨 배치·완성형 예시 지시 정밀화가 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★개선 — 별표 표 정리 라벨 배치 재현(v0.26.0 관찰 A 축 재실행)",
        "probe_prompt": "자율주행기술개발혁신사업 사업단장은 어떤 절차와 기준으로 선정되는지 별표까지 포함해 표로 정리해줘.",
        "expect_behavior": "v0.26.0 eval P1 재실행 — 별표 1(선정절차)·별표 2(선정기준 배점)를 표·목록으로 정리할 때 "
                           "인용·재구성·요약 방식 라벨 단어가 해당 표·목록의 캡션(제목 줄) 또는 바로 앞·뒤 문장에 "
                           "표시되는지(★핵심 — v0.26.0 관찰 A는 라벨 단어 미명시·예시 관용구 \"…— 재구성(내용 보존 "
                           "표 정리)\" 형태 준수가 이상적). 배점 수치(20/25/25/30=100)는 도구 grounded 유지 + 표 작성 "
                           "자체를 회피하지 않는지(over-blocking 없음).",
    },
    {
        "category": "★개선 — 혼합 종합표 라벨+위치 재현(v0.25.0 minor C 축 재실행)",
        "probe_prompt": "국방연구개발 시설·장비 규정에서 장비 등록 절차와 관련 별표 내용을 종합해서 하나의 표로 정리해줘.",
        "expect_behavior": "v0.25.0 eval P2 유사 재실행 — 조문(제9조 정보등록)과 별표(등록번호 체계 등)를 섞은 혼합 "
                           "종합표에서 별표 사용 부분의 방식 라벨이 캡션 또는 앞·뒤 문장에 명시되는지(★핵심 — "
                           "v0.25.0 minor C는 정리 표에 방식 라벨 미명시). 별표 8 oversized면 annex_chunk 경로 사용 "
                           "+ 부분성 고지 유지.",
    },
    {
        "category": "무회귀 — 값 정확성·기존 지시 무간섭(라벨 지시 추가가 내용 정확성을 훼손하지 않는지)",
        "probe_prompt": "연구실 안전교육 시간을 연구활동종사자 유형별로 표로 정리해줘.",
        "expect_behavior": "연구실안전법 시행규칙 별표 3 재구성 표 — 교육시간 수치(신규 8/4/2h·정기 연3/반기6/반기3h· "
                           "특별 2h)의 조건-값 귀속이 정확한지(v0.24.1 지시 유지)와 방식 라벨이 캡션/인접 문장에 "
                           "표시되는지 동시 확인. 라벨 지시가 값 정확성·표 구성 품질을 희석하지 않아야 정상.",
    },
]
