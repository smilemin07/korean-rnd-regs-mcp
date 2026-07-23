"""v0.24.0 배포 전 LIVE acceptance spec — 「국방 트랙 2차 — 업무처리지침·기술료 고시 등록(58→60) + 캐시 상한 96」.

읽는 법(비프로그래머용): 이번 v0.24.0은 rule_sets.yaml 데이터 2건 추가 + 프롬프트 라우팅 문자열 +
캐시 상수 2줄(64→96)이며 코드 알고리즘·응답 schema 변경이 없습니다(순수 data 확대 12번째).
Level A(자동)는 ① 신규 2건이 LIVE에서 실제 도달·조회되는지(정확 제목 resolve·별표 tier-1·
amendment_kind) ② 기존 경로가 그대로인지(무회귀) ③ N=60 cold fan-out이 예산 내인지 확인합니다.
소비 품질(실무 절차 질의·기술료 라우팅·트랙 가드 유지)은 호스트 LLM 행동(Level B)이라 배포 후
라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

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
        "name": "신규 A — 국방 5건 fan-out 도달('국방과학기술' — N=60 첫 cold fan-out·신규 2건 본문에 「국방과학기술혁신 촉진법」 인용 실측)",
        "tool": "search_provision",
        "args": {"query": "국방과학기술"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_act"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_decree"},
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_rule"},
            {"kind": "fetched_ok", "rule_set_id": "defense_rnd_guideline"},        # ★v0.24.0 신규
            {"kind": "fetched_ok", "rule_set_id": "defense_tech_fee_notice"},      # ★v0.24.0 신규
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 18.0},                                         # WARN — cold N=60(v0.23.1 실측 7.53s@58)
        ],
    },
    {
        "name": "신규 B — 업무처리지침 별표 tier-1(admrul:2100000274666:BP0001 — 재프로브 별표 7 전건 tier-1·최대 ~4.3k자)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274666:BP0001"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 별표 도달
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier-1 전문
        ],
    },
    {
        "name": "신규 C — 업무처리지침 문서레벨 도달+amendment_kind(admrul:2100000274666 — 일부개정·개정문내용 부재=kind만 부착 정상)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274666"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 정확 제목 resolve 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},            # WARN — 2026-07-23 재프로브 실측
        ],
    },
    {
        "name": "신규 D — 기술료 고시 문서레벨 도달(admrul:2100000274638 — ㆍ U+318D 제목 resolve·별표 0=article)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000274638"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — ㆍ 포함 제목 resolve 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},            # WARN — 재프로브 실측
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
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(N=60·캐시 96이 검색 경로 무해)",
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.24.0 = 신규 2건 소비 품질 + 트랙 가드 무회귀.
LEVEL_B_PROMPTS = [
    {
        "category": "★신규 — 업무처리지침 소비(방사청 R&D 실무 절차 grounded)",
        "probe_prompt": "방위사업청 핵심기술 연구개발사업은 어떤 절차로 진행돼? 근거 규정 조문과 함께 알려줘.",
        "expect_behavior": "국방기술 연구개발 업무처리지침(예규 제1045호)이 검색·상세 조회로 grounded되는지(★핵심 — "
                           "v0.23.0까지는 미지원이라 법·시행령 골격만 가능했음). 국방과기법 제8조 위임 구조(법→지침) "
                           "위계가 유지되고, 지침 조문 번호·원문 인용이 도구 응답 기반인지. 미지원이던 시절처럼 "
                           "외부 웹검색으로 폴백하지 않는지.",
    },
    {
        "category": "★신규 — 국방 기술료 라우팅(3규정 혼동 없음)",
        "probe_prompt": "국방 R&D 과제의 기술료는 어떻게 산정하고 납부해?",
        "expect_behavior": "국방과학 기술료 고시(고시 제2026-4호)가 grounded되는지(★핵심). 산업부 기술료 통합요령· "
                           "중기부 기술료 관리규정과 혼동 없이 국방 트랙으로 라우팅되는지(제목·소관 구분). 법 제11조· "
                           "시행령 제14조 위임 연결이 정확한지. 별지 서식(BP 미노출)을 본문으로 날조하지 않는지.",
    },
    {
        "category": "무회귀 — 트랙 가드·참여제한 유지(+지시② 혼합 종합표 자연 관측)",
        "probe_prompt": "국방 R&D 과제 참여제한 기준을 표로 정리해줘.",
        "expect_behavior": "v0.23.1 eval P3 재실행 — 법 제9조①+시행령 별표1 수치가 도구 grounded로 유지되고 '혁신법과 "
                           "별도 체계' 구분 유지(신규 2건 등록이 기존 가드를 희석하지 않아야 정상). ★부수 관측: 법+령+ "
                           "별표 혼합 종합표에 인용·재구성·요약 방식 라벨이 붙는지 — v0.23.1 유일 minor의 자연 표본 "
                           "+1(차기 지시② 문면 정교화의 설계 입력·이번 릴리스 판정에는 비감점).",
    },
]
