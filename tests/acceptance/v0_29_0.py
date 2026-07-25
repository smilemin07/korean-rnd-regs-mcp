"""v0.29.0 배포 전 LIVE acceptance spec — 「규정 상세 응답 하단 표준 안내(standard_footer) — A-1 경로 응답 구조화」.

읽는 법(비프로그래머용): 이번 v0.29.0은 get_provision_detail 성공 응답에 답변 하단 표준 안내
1줄(standard_footer)을 추가한 릴리스입니다. v0.28.0 eval에서 "서버가 완성형을 주면 붙고(2/2),
AI가 직접 조립해야 하면 안 붙는다(누적 0/5)"가 실증되어, 매뉴얼을 쓰지 않는 규정 답변 경로에도
서버 완성형을 공급합니다. 성공 반환점 3곳(문서레벨·조문·별표)에 헬퍼 1개를 거는 최소 변경이며
기존 필드·tier 판정·백스톱은 완전 불변입니다. Level A(자동)는 ① 기존 무회귀와 ② 신규 필드의
결정론 확인(3경로 footer 글자 단위 일치·매뉴얼 무회귀)을 수행합니다. 개선의 핵심(호스트가 footer를
실제로 부착하는가)은 Level B로 배포 후 사람이 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]
"""

_A1 = "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 법령·행정규칙 원문을 기준으로 해주시기 바랍니다."

CHECKS = [
    {
        "name": "무회귀 A — 자율주행 검색 도달 유지('자율주행' fan-out)",
        "tool": "search_provision",
        "args": {"query": "자율주행"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "kt_autonomous_driving"},                   # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN
        ],
    },
    {
        "name": "★신규 A — 문서레벨 성공 응답 footer 글자 단위 일치(admrul 사용기준)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278740"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "standard_footer", "value": _A1},                # WARN — 신규
        ],
    },
    {
        "name": "★신규 B — 조문(JO) 성공 응답 footer + 기존 필드 무회귀(혁신법 제13조)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _A1},                # WARN — 신규
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 무회귀
        ],
    },
    {
        "name": "★신규 C — 별표(BP) oversized_pointer에도 footer + tier 무회귀(law:285767:BP0002)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 무회귀
            {"kind": "field_equals", "path": "standard_footer", "value": _A1},                # WARN — 신규
        ],
    },
    {
        "name": "무회귀 D — 매뉴얼 도구 불변(3-9 citation·footer 3줄 유지 — v0.28.0 승계)",
        "tool": "get_manual_section",
        "args": {"section_id": "3-9"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가연구개발혁신법 매뉴얼(본권)」(26.4판) 제3장 제9절 보안수당 사용용도 및 사용기준, 인쇄 p.243~244"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.29.0 = 규정-only 답변의 A-1 부착 발현(직전 0/2 축 재측정).
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 규정-only 답변 A-1 부착(직전 0/2·누적 0/5 축)",
        "probe_prompt": "국가연구개발혁신법 제13조 조문 원문을 보여줘.",
        "expect_behavior": "기존 규정 도구로 조문 원문 verbatim 제공(매뉴얼 미호출). ★핵심 관측: 답변 마지막에 "
                           "규정 응답의 standard_footer 1줄이 그대로 1회 부착되는지(v0.28.0 eval에서 0/2였던 "
                           "바로 그 프로브 — 서버 완성형 공급 후 개선 여부의 직접 재측정). 매뉴얼 고지 오부착 0 유지.",
    },
    {
        "category": "★표적 — 매뉴얼 인용 답변은 3줄 유지 + 1줄 중복 부착 0(단일 분기 규칙)",
        "probe_prompt": "회의비로 식비를 쓸 때 사전결재를 꼭 받아야 하는지, 매뉴얼 해설까지 확인해서 실무 기준으로 정리해줘.",
        "expect_behavior": "법령+매뉴얼 병행 확인 후 매뉴얼 3줄 standard_footer만 부착하는지(규정 응답의 1줄을 "
                           "이어 붙이는 중복 없음 — 첫 줄이 동일 문자열). footer 블록이 답변당 정확히 1개인지.",
    },
    {
        "category": "관찰 — 잔존 경로(검색·추천만 보고 답하는 경우) 빈도",
        "probe_prompt": "연구개발비 사용 기준에서 회의비 관련 조항이 어디에 있는지만 빠르게 알려줘.",
        "expect_behavior": "호스트가 get_provision_detail 없이 검색 결과만으로 답하면 footer 미부착 갭이 잔존 — "
                           "그 빈도를 관측(발생 시 후속 릴리스에서 suggest/search 확대 여부 판단 자료). "
                           "원문 확인까지 갔다면 footer 1줄 부착 여부 관측.",
    },
]
