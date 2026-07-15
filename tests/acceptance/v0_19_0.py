"""v0.19.0 배포 전 LIVE acceptance spec — 「admrul redline 확장 — 행정규칙 문서레벨 amendment_text·amendment_kind」.

읽는 법(비프로그래머용): 이번 v0.19.0은 v0.17.0에서 법령(law)에만 제공하던 "이번 개정으로 무엇이 바뀌었나"
데이터(amendment_text=개정문 산문·amendment_kind=제개정구분)를 행정규칙(admrul: 고시·예규·훈령) 문서레벨
응답으로 확장합니다(입력 파라미터 무변·응답 additive만). 자동(Level A) 검증은 ① 개정문 보유 행정규칙(시설장비
표준지침 — LIVE 실측 최대 3,836자)에서 amendment_text가 실제 부착되는지 ② 개정문 부재군(연구개발비 사용 기준 —
일부개정인데도 부재)에서 kind만 정직하게 부착되는지 ③ 기존 law 경로·검색이 회귀하지 않았는지를 확인합니다.
호스트 LLM이 admrul 개정문을 올바로 소비하는지(부재≠무개정·전수 열거)는 Level B라 배포 후 라이브 커넥터에서
사람이 아래 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★신기능 검증(핵심 A·B)은 전부 WARN 클래스(field_equals·absent_error_code)로만 구성 — LIVE 개정문 제공
  여부·제개정구분 값은 법제처 데이터 사정(추가 개정 발생 등)에 따라 변할 수 있어 hard-BLOCK 부적합
  (false-block-safe·Andy 최우선 끊김없음). BLOCK 후보(fetched_ok·returned_not_below)는 기존 무회귀
  검색 체크에만 둔다.
"""

CHECKS = [
    {
        "name": "핵심 A — admrul 개정문 부착(시설장비 표준지침 admrul:2100000278230 → amendment 필드·LIVE 최대 3,836자 통째 부착)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278230"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 문서 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — 제개정구분명 정규화 캡처(2026-07-15 실측)
            {"kind": "field_equals", "path": "amendment_text_omitted", "value": "<missing>"},  # WARN — 생략 미발동(run.py는 부재 경로를 '<missing>'으로 해석)
        ],
    },
    {
        "name": "핵심 B — 부재 정직(연구개발비 사용 기준 admrul:2100000278740 → 일부개정인데 개정문 부재·kind만 부착)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278740"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — 부재군도 kind는 부착(★부재≠무개정)
            {"kind": "field_equals", "path": "amendment_text", "value": "<missing>"},      # WARN — text 미출현(태그 자체 부재·결정론 — run.py '<missing>' 해석)
        ],
    },
    {
        "name": "무회귀 A — law 문서레벨 amendment 경로 무변(혁신법 law:283849 amendment_kind='일부개정' 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — v0.17.0 부착 경로 무회귀
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(파서 findtext 2건 추가가 검색 fan-out 무해)",
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.19.0 = 호스트의 admrul amendment 소비 품질.
LEVEL_B_PROMPTS = [
    {
        "category": "★핵심 — admrul 개정문 발견·소비",
        "probe_prompt": "국가연구개발 시설·장비의 관리 등에 관한 표준지침이 이번 개정으로 뭐가 바뀌었는지 알려줘",
        "expect_behavior": "호스트가 admrul 문서레벨 get_provision_detail의 amendment_text(개정지시문 산문·"
                           "'제5조제4항제3호 중 …을 …으로 한다' 등)와 amendment_kind='일부개정'으로 답하고, "
                           "외부 웹 우회 없이 개정 지시 항목을 빠짐없이 정리(v0.17.1 가이드가 admrul에도 적용).",
    },
    {
        "category": "★부재 정직 — 일부개정인데 개정문 없음(최대 사용처)",
        "probe_prompt": "국가연구개발사업 연구개발비 사용 기준은 최근 개정에서 뭐가 바뀌었어?",
        "expect_behavior": "rnd_funding_standard(2100000278740)는 일부개정(kind 부착)인데 개정문 부재(2026-07-15 LIVE "
                           "실측). 호스트가 amendment_text 부재를 '개정되지 않았다'로 단정하지 않고(★부재≠무개정 가이드 "
                           "소비) document_source_url 공식 원문으로 우회 안내.",
    },
    {
        "category": "제정 skip — admrul 제정 문서(전체 신설 신호)",
        "probe_prompt": "혁신도전형 연구개발사업군 지정 및 분류 등에 관한 기준은 어떤 개정 이력이 있어?",
        "expect_behavior": "innovation_challenge_criteria는 제정(kind='제정')·amendment_text 미제공(제정문=발령 메타라 "
                           "skip). 호스트가 '전체 신설(제정)'로 정확히 안내하고 없는 개정 delta를 날조하지 않음.",
    },
    {
        "category": "무회귀(개정과 무관한 grounding)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "admrul 확장이 기존 law 조문 검토를 회귀시키지 않음.",
    },
]
