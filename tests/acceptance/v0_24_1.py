"""v0.24.1 배포 전 LIVE acceptance spec — 「v0.24.0 eval 관측 소비 결함 2건 해소 — 혼합 종합표 방식 라벨 포섭 + 조건-값 결합 보존」.

읽는 법(비프로그래머용): 이번 v0.24.1은 코드 로직·응답 schema 변경이 전혀 없는 프롬프트 문자열-only
patch입니다(v0.17.1·v0.19.1·v0.20.1·v0.21.1·v0.23.1과 동형·6번째). 서버가 반환하는 데이터는 v0.24.0과
동일해야 하므로 Level A(자동)는 무회귀 확인만 수행합니다 — ① 국방 트랙 5건 검색 도달(v0.24.0 신규 2건
포함) · 지침 별표 tier-1·기본 경로(oversized_pointer)·청크·amendment 부착이 그대로인지 ② 검색 fan-out
recall이 유지되는지. 개선 자체(혼합 종합표의 인용·재구성·요약 방식 라벨 · 조건-값 한정어 귀속 보존)는
호스트 LLM 행동(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★별표·amendment 관련 항목은 전부 WARN 클래스 — 별표가 개정으로 예산 내 크기로 줄면 기본 경로가
  전문 verbatim으로 바뀌고, amendment_kind는 LIVE 개정에 따라 변하는 것이 정상 거동이라
  hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음). BLOCK 후보는 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "무회귀 A — 국방 트랙 검색 도달 유지('국방과학기술' fan-out — family 3건 + v0.24.0 신규 2건)",
        "tool": "search_provision",
        "args": {"query": "국방과학기술"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_act"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_decree"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_rule"},
            {"kind": "fetched_ok", "rule_set_id": "defense_rnd_guideline"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_fee_notice"},
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
        ],
    },
    {
        "name": "무회귀 B — 지침 별표 tier-1 유지(admrul:2100000274666:BP0001 — v0.24.0 실측 승계)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274666:BP0001"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 유지
        ],
    },
    {
        "name": "무회귀 C — 기본 경로 무변(law:285767:BP0002 opt-in 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 기본 경로 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 포인터 인용 금지 유지
        ],
    },
    {
        "name": "무회귀 D — 청크 조회 유지(law:285767:BP0002 annex_chunk=1 → verbatim 청크·v0.20.0 기능)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002", "annex_chunk": 1},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 청크 원문 유지
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN — 부분성 메타 유지
        ],
    },
    {
        "name": "무회귀 E — admrul 문서레벨 amendment 부착 유지(기술료 고시 amendment_kind=일부개정 — v0.24.0 실측 승계)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274638"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},            # WARN — 2026-07-23 LIVE 실측 일치
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.24.1 = 소비 정확성 지시 정밀화가 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★개선① — 혼합 종합표 방식 라벨 재현(v0.23.1 P3·v0.24.0 P3 표본 축)",
        "probe_prompt": "국방 R&D 과제 참여제한 기준을 법·시행령·별표를 종합해서 표 하나로 정리해줘.",
        "expect_behavior": "v0.24.0 eval P3 재실행 — 법 제9조①+시행령 별표1을 혼합한 종합표를 만들 때 별표 사용 "
                           "부분의 방식(인용·재구성·요약)이 답변에 명시되는지(★핵심 — '기준으로 정리했습니다'류 "
                           "부분 고지만으로는 미달). 참여제한 수치(2년·재범 5년·가중 1/2·합산 5년)는 도구 grounded "
                           "유지 + 종합표 작성 자체를 회피하지 않는지(over-blocking 없음).",
    },
    {
        "category": "★개선② — 조건-값 결합 보존 재현(v0.24.0 P2 압축 오류 축)",
        "probe_prompt": "국방과학 기술료 고시의 기술료 감면 기준을 기업 유형별로 알려줘.",
        "expect_behavior": "v0.24.0 eval P2 재실행 — 고시 제5조④4호의 2계층 조건(가호: 중소기업+유예기간 내[3년 "
                           "미경과] 중견기업=50% / 나호: 그 외 중견기업=25%)을 압축할 때 '유예기간 내' 한정어가 "
                           "50% 쪽(가호)에 정확 귀속되는지(★핵심 — v0.24.0 minor는 25% 쪽 오귀속). 대응이 "
                           "불확실하면 가/나호 원문 구조대로 나눠 표시하는 폴백도 정상. 요율(1%/10%/2%/3%)· "
                           "70% 누적 한도 등 인접 수치 정확성 유지.",
    },
    {
        "category": "무회귀 — 기존 별표 단독 방식 라벨(v0.23.1 지시② 실효)·트랙 가드 무간섭",
        "probe_prompt": "국방과학기술혁신 촉진법 시행규칙 별표의 연구개발비 사용용도를 표로 정리해줘.",
        "expect_behavior": "v0.23.1 eval P2 재실행 — 별표 단독 재구성 표에 '재구성' 라벨 명시가 유지되는지(신규 "
                           "혼합 종합표 문구가 기존 단독 케이스 라벨을 희석하지 않아야 정상). 항목 구조·출처· "
                           "원문 대조 권고 유지 + 표 정리 자체를 회피하지 않는지(over-blocking 없음).",
    },
]
