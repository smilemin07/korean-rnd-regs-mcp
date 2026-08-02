"""v0.31.0 배포 전 LIVE acceptance spec — 「혁신법 매뉴얼 본권 26.7판 현행화」.

읽는 법(비프로그래머용): 이번 v0.31.0은 임베드 매뉴얼 데이터를 26.4판에서 26.7판으로 전체
교체한 릴리스입니다(41→43절·법령 시행일 2026.6월 기준·인쇄 1~332쪽·[부록]은 별도 PDF 분리).
★제3장에 제12절(연구혁신비)이 신설되어 구판 3-12~3-19의 주제가 3-13~3-20으로 이동했고,
영향 절의 get_manual_section 응답에만 manual_meta.renumbering_note(재번호 안내)가 additive로
붙습니다. 규정 5종 도구는 완전 무변 — 무회귀 확인만 합니다. Level A(자동)는 새 데이터의
결정론 값(판번·절 수·재번호 id·note 부착/미부착)과 기존 무회귀. 개선의 핵심(호스트가 신판
데이터·재번호 안내를 올바르게 소비하는가)은 Level B로 배포 후 사람이 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]
"""

_LAW_LINE = "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다."
_MANUAL_SOURCE_LINE = (
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)
_PROVISION_FOOTER = _LAW_LINE + "\n" + _MANUAL_SOURCE_LINE
_SOURCE_URL_267 = "https://www.kistep.re.kr/board.es?mid=a10301000000&bid=0003&act=view&list_no=94788"
_RENUMBERING_NOTE = (
    "26.7판에서 제3장 제12절 「연구혁신비 사용용도 및 사용기준」이 신설되어, "
    "26.4판 제3장 제12~19절의 주제는 26.7판 제13~20절로 각각 이동했습니다. "
    "section_id는 현행 수록 판(26.7판)의 장-절 번호입니다. 구판 번호로 조회했다면 "
    "이 응답의 section_title·citation을 확인하고, 필요한 절은 search_manual로 다시 찾으십시오."
)
_FOOTER_4LINES_267 = (
    _PROVISION_FOOTER + "\n"
    "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
    "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다.\n"
    "※ 인용 매뉴얼: 26.7판 · 법령 시행일 2026-06 기준"
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(규정 트랙 완전 무변 확인)",
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
        "name": "무회귀 — 규정 상세 footer 2줄(문면 무변·데이터 교체 무영향)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "★신규 A — 매뉴얼 검색이 26.7판 데이터로 응답(43절·신설 절 도달)",
        "tool": "search_manual",
        "args": {"query": "연구혁신비"},
        "asserts": [
            # 주의: returned_not_below는 search_provision의 results 키 전용(런너 동결) —
            # search_manual은 로컬 결정론 데이터이므로 field_equals(WARN)로 검증.
            {"kind": "field_equals", "path": "returned", "value": 3},                         # WARN — 신규(26.7 실측)
            {"kind": "field_equals", "path": "scanned_sections", "value": 43},                # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.edition", "value": "26.7"},         # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.renumbering_note", "value": "<missing>"},  # WARN — search 미부착
        ],
    },
    {
        "name": "★신규 B — 신설 3-12(연구혁신비) 상세 + renumbering_note 부착 + 26.7 footer 4줄",
        "tool": "get_manual_section",
        "args": {"section_id": "3-12"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "section_title", "value": "연구혁신비 사용용도 및 사용기준"},  # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.source_url", "value": _SOURCE_URL_267},  # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.standard_footer", "value": _FOOTER_4LINES_267},  # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.renumbering_note", "value": _RENUMBERING_NOTE},  # WARN — 대상 절 부착
        ],
    },
    {
        "name": "★신규 C — 재번호 양 끝 잠금: 3-13=간접비(구 3-12) 제목 확인",
        "tool": "get_manual_section",
        "args": {"section_id": "3-13"},
        "asserts": [
            {"kind": "field_equals", "path": "section_title", "value": "간접비 사용용도 및 사용기준"},  # WARN — 신규
        ],
    },
    {
        "name": "★신규 D — 3-20=연구시설･장비비 통합관리(구 3-19) + note 부착",
        "tool": "get_manual_section",
        "args": {"section_id": "3-20"},
        "asserts": [
            {"kind": "field_equals", "path": "section_title", "value": "연구시설･장비비 통합관리"},  # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.renumbering_note", "value": _RENUMBERING_NOTE},  # WARN — 대상 절 부착
        ],
    },
    {
        "name": "★신규 E — 안정 id 3-4(학생인건비)는 주제 유지 + note 미부착(비대상)",
        "tool": "get_manual_section",
        "args": {"section_id": "3-4"},
        "asserts": [
            {"kind": "field_equals", "path": "section_title", "value": "학생인건비 사용용도 및 사용기준"},  # WARN — 무회귀
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 26.7 실측 tier
            {"kind": "field_equals", "path": "manual_meta.renumbering_note", "value": "<missing>"},  # WARN — 비대상 미부착
        ],
    },
    {
        "name": "★신규 F — 신규 참고 ref-3(행정서식 관리체계) 조회 가능",
        "tool": "get_manual_section",
        "args": {"section_id": "ref-3"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 신규
            {"kind": "field_equals", "path": "section_title", "value": "국가연구개발사업 행정서식 관리체계"},  # WARN — 신규
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.31.0 = 신판 데이터 소비·재번호 안내 실효.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 신설 절(연구혁신비) 해설이 신판 기준으로 전달되는가",
        "probe_prompt": "혁신법 매뉴얼에서 연구혁신비의 사용용도와 사용기준 해설을 찾아 인쇄쪽과 함께 알려줘.",
        "expect_behavior": "search_manual·get_manual_section으로 3-12(연구혁신비)를 찾아 26.7판 citation"
                           "(인쇄 p.249~252)과 4줄 footer(26.7판 notice)를 부착하는지. 판번이 26.4로 "
                           "표기되는 곳이 없는지.",
    },
    {
        "category": "★표적 — 재번호 절(간접비) 질의가 신판 위치(3-13)로 정확히 도달 + note 소비",
        "probe_prompt": "혁신법 매뉴얼에서 간접비 사용용도 해설을 찾아 몇 장 몇 절인지와 함께 설명해줘.",
        "expect_behavior": "search-first로 3-13(제3장 제13절 간접비)에 도달하는지(구판 3-12로 오표기 없음). "
                           "manual_meta.renumbering_note가 응답에 있을 때 호스트가 구판·신판 번호를 혼동하지 "
                           "않는지 관측(안내 문구의 답변 내 발현 여부도 기록 — 발현 자체는 요구 아님).",
    },
    {
        "category": "관찰 — 법령·매뉴얼 병행 답변의 기준일 표기(2026.6월 기준 신판 정합)",
        "probe_prompt": "학생인건비 계상 기준을 법령 조문과 매뉴얼 해설을 함께 확인해서 설명해 주세요.",
        "expect_behavior": "법령 조문(get_provision_detail)과 매뉴얼(3-4·안정 id) 병행 인용 시 매뉴얼 쪽에 "
                           "26.7판·법령 시행일 2026-06 기준이 표기되는지. 4줄 footer 1블록(중복 0) 무회귀.",
    },
]
