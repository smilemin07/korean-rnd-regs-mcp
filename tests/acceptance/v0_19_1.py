"""v0.19.1 배포 전 LIVE acceptance spec — 「eval 근본원인 프롬프트 가이드 보강 — 구체값 단정 금지 확장 + '개정 이력·연혁' 질의 라우팅」.

읽는 법(비프로그래머용): 이번 v0.19.1은 프롬프트 문자열만 바꾸는 patch입니다(코드 로직·응답 데이터 무변 —
v0.17.1과 동형). 따라서 자동(Level A) 검증은 전부 "기존 기능이 회귀하지 않았는지"만 봅니다(v0.19.0의
admrul amendment 부착·제정 skip·law 경로·검색 recall 유지). 이번 개선 자체(호스트가 원문에 없는 구체값을
임의 예시로 만들지 않는지 · '개정 이력/연혁' 질의를 웹보다 서버 데이터로 먼저 라우팅하는지)는 호스트 LLM
행동(Level B)이라 자동 검증이 불가능하며, 배포 후 라이브 커넥터에서 사람이 아래 LEVEL_B_PROMPTS로 수동
확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★무회귀 체크의 amendment 관련 항목은 전부 WARN 클래스(field_equals·absent_error_code) — LIVE 개정문
  제공 여부·제개정구분 값은 법제처 데이터 사정(추가 개정 발생 등)에 따라 변할 수 있어 hard-BLOCK 부적합
  (false-block-safe·Andy 최우선 끊김없음). BLOCK 후보(fetched_ok·returned_not_below)는 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "무회귀 A — admrul 개정문 부착 유지(시설장비 표준지침 admrul:2100000278230 → v0.19.0 amendment 필드)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278230"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 문서 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — v0.19.0 부착 경로 무회귀(2026-07-15 실측)
            {"kind": "field_equals", "path": "amendment_text_omitted", "value": "<missing>"},  # WARN — 생략 미발동(run.py는 부재 경로를 '<missing>'으로 해석)
        ],
    },
    {
        "name": "무회귀 B — 부재 정직 유지(연구개발비 사용 기준 admrul:2100000278740 → 일부개정·개정문 부재·kind만)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278740"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — 부재군도 kind는 부착(★부재≠무개정)
            {"kind": "field_equals", "path": "amendment_text", "value": "<missing>"},      # WARN — text 미출현(태그 자체 부재·결정론)
        ],
    },
    {
        "name": "무회귀 C — law 문서레벨 amendment 경로 무변(혁신법 law:283849 amendment_kind='일부개정' 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — v0.17.0 부착 경로 무회귀
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(프롬프트 문자열 patch가 검색 경로 무해)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                  # 실측 ~16-17·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.19.1 = 신규 2지시의 호스트 소비 품질이 개선 그 자체.
LEVEL_B_PROMPTS = [
    {
        "category": "★P4 재현 — 원문에 없는 구체값 임의 예시 금지",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘. 실무에서 지켜야 할 "
                        "기한이 있으면 그것도 알려줘.",
        "expect_behavior": "v0.19.0 eval P4에서 호스트가 '처리기한(예: 15일 이내 통보)' 같은 도구 미확인 임의 예시를 "
                           "출력했던 시나리오. 신 가이드로 원문(법§11·시행령§14 등)에 없는 기한·수치를 임의 예시로 "
                           "단정하지 않고 'MCP 응답에서 확인되지 않음' 취지로 처리하는지 확인.",
    },
    {
        "category": "★P3 재현 — '개정 이력' 표현 질의의 서버-first 라우팅",
        "probe_prompt": "혁신도전형 연구개발사업군 지정 및 분류 등에 관한 기준은 어떤 개정 이력이 있어?",
        "expect_behavior": "v0.19.0 eval P3에서 웹-first·MCP 미호출이던 그 질의. 신 라우팅 지시로 문서레벨 "
                           "get_provision_detail을 먼저 호출해 amendment_kind='제정'을 확인하고, 서버가 반환한 최신 "
                           "제·개정구분 기준으로 제정 이후 개정 이력이 없다고 정직하게 답하며(없는 delta 날조 0), "
                           "전체 연혁 미제공 한계를 밝히는지 확인.",
    },
    {
        "category": "★over-blocking 방지 — 원문 실재 수치는 위축 없이 인용",
        "probe_prompt": "국가연구개발사업 연구개발비 사용 기준에서 회의비·식비 관련 금액 기준을 원문 근거와 함께 알려줘.",
        "expect_behavior": "신 P4 가드가 도구 유래 수치 인용까지 위축시키지 않는지 확인 — 도구 응답 원문에 실재하는 "
                           "금액·기준을 hedging 없이 그대로 인용하고(원문 verbatim), 원문에 없는 값만 확인되지 않음 "
                           "처리하는지(인용 허용/금지 양립 실증).",
    },
    {
        "category": "무회귀 — 기존 amendment 소비 지시(전수 열거·citation 보존)와의 상호 간섭 없음",
        "probe_prompt": "중소기업 기술혁신 촉진법이 최근 개정으로 뭐가 바뀌었는지 빠짐없이 알려줘",
        "expect_behavior": "v0.17.1 검증 시나리오 재실행 — 신규 2지시 삽입 후에도 amendment_text 개정 지시 항목을 "
                           "가지조문 포함 전수 열거하고 근거 법률 인용을 보존하는지(기존 지시와의 상호 간섭·희석 없음).",
    },
]
