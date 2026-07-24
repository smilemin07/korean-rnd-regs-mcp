"""v0.26.0 배포 전 LIVE acceptance spec — 「국토교통 트랙 실무 확대(63→64) — (국토교통부) 자율주행기술개발혁신사업 운영관리규정 등록」.

읽는 법(비프로그래머용): 이번 v0.26.0은 rule_sets.yaml 데이터 1건 추가 + 프롬프트 라우팅 문자열이며
코드 알고리즘·응답 schema·캐시 상수 변경이 없습니다(순수 data 확대 14번째·캐시 96은 N=64에서
headroom 32). Level A(자동)는 ① 신규 1건이 LIVE에서 실제 도달·조회되는지(★부처 접두 제목
"(국토교통부) …" verbatim resolve 검증 겸함 — 무접두 제목은 정확일치 0행 함정) ② 별표 3건이
tier-1 원문 전문으로 오는지 ③ 기존 경로가 그대로인지(무회귀) ④ N=64 cold fan-out이 예산 내인지
확인합니다. 소비 품질(사업단장 선정·기술료 조문 grounded·공동 운영관리규정 구분)은 호스트 LLM
행동(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★별표·amendment 관련 항목은 전부 WARN 클래스 — 별표 크기·제개정구분은 LIVE 개정에 따라 변하는
  것이 정상 거동이라 hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는
  검색 도달·recall에만.
"""

CHECKS = [
    {
        "name": "신규 A — 자율주행 fan-out 도달('자율주행' 무접두 자연어 — N=64 첫 cold fan-out·접두 제목 resolve 검증 겸함)",
        "tool": "search_provision",
        "args": {"query": "자율주행"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "kt_autonomous_driving"},                   # ★v0.26.0 신규 — 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 18.0},                                         # WARN — cold N=64(v0.25.0 실측 2.44s@63)
        ],
    },
    {
        "name": "신규 B — 자율주행 문서레벨 도달+amendment_kind(admrul:2100000282292 — 접두 제목 정확일치 resolve·타법개정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282292"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 접두 제목 resolve 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "타법개정"},            # WARN — 2026-07-24 재프로브 실측(부처명 정비)
        ],
    },
    {
        "name": "신규 C — 자율주행 별표 3 tier-1 원문(admrul:2100000282292:BP0003 — 사업단·사업단장 평가절차·escaped 4,960)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282292:BP0003"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 본문 전문
        ],
    },
    {
        "name": "무회귀 A — 기본 경로 무변(law:285767:BP0002 opt-in 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 B — 국토교통 기존 규정 도달('연구개발사업 운영' — kt_rnd_operations 병존·오집 없음)",
        "tool": "search_provision",
        "args": {"query": "연구개발사업 운영"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "kt_rnd_operations"},                       # 기존 국토교통 rank 4 무회귀
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(N=64가 검색 경로 무해)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 실측 ~16-17·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN — warm 경로
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.26.0 = 신규 1건 소비 품질 + 병존 규정 구분.
LEVEL_B_PROMPTS = [
    {
        "category": "★신규 — 자율주행 규정 소비(사업단장 선정 절차 grounded + 별표 소비)",
        "probe_prompt": "자율주행기술개발혁신사업의 사업단장은 어떤 절차와 기준으로 선정돼? 근거 규정 조문과 함께 알려줘.",
        "expect_behavior": "(국토교통부) 자율주행기술개발혁신사업 운영관리규정(훈령 제1967호)이 검색·상세 조회로 grounded되는지"
                           "(★핵심 — v0.25.0까지는 미지원이라 외부 웹 폴백·stale 위험 구간). 제11조(사업단장의 선정)와 "
                           "별표 1(선정절차)·별표 2(선정기준)를 도구 원문 기반으로 인용하는지. 별표 정리 시 인용·재구성·요약 "
                           "방식 라벨을 명시하는지(v0.24.1 지시).",
    },
    {
        "category": "★신규 — 자율주행 기술료·과제 운영 소비(조문 grounded + 상위 규정 위계)",
        "probe_prompt": "자율주행기술개발혁신사업 과제에서 기술료 징수와 사용은 어떻게 정해져 있어?",
        "expect_behavior": "제28조(기술료의 징수)·제29조(기술료의 사용)가 도구 응답 기반으로 인용되는지(★핵심). "
                           "혁신법·시행령 등 상위 규정과의 위계(상위 우선 적용)를 함께 안내하는지. 도구 원문에 없는 "
                           "요율·수치를 임의로 단정하지 않는지.",
    },
    {
        "category": "★구분 — 공동 운영관리규정(과기부·산업부)과의 별개 문서 구분",
        "probe_prompt": "자율주행기술개발혁신사업 운영관리규정이 여러 부처에 있다고 하던데, 국토교통부 규정이 맞아?",
        "expect_behavior": "등록된 (국토교통부) 운영관리규정과 미등록인 과기정통부·산업통상부의 '… 공동 운영관리규정'"
                           "(별개 문서)을 혼동하지 않는지. 미등록 문서의 구체 내용을 현행 사실로 단정하지 않고 "
                           "일반 학습지식 라벨 또는 확인 불가로 처리하는지(v0.23.1 지시).",
    },
]
