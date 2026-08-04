"""v0.33.0 배포 전 LIVE acceptance spec — 「혁신법 매뉴얼 별권 2 기술료 제도 매뉴얼 수록」.

읽는 법(비프로그래머용): 이번 v0.33.0은 별권 2(기술료 제도 매뉴얼·15단위·인쇄 1~12쪽)를
기존 매뉴얼 도구 2종에 통합한 릴리스입니다. 새 도구는 없고(7종 유지) 입력 파라미터 구조도
그대로라 웹 커넥터 재연결이 필요 없습니다. 코드 축의 유일한 구조 변경은 교차 소스 층의
descriptor 일반화(3소스 병합)라, Level A(자동)는 별권 2 조회·검색 도달·3소스 혼합 계측과
**규정 트랙·본권·별권 3 무회귀(보존 표면)**를 결정론으로 확인합니다. 개선의 핵심(호스트가
기술료 구체값을 시행령 원문으로 교차 확인하는가·구판 용어를 현행 용어로 정정하는가)은
Level B로 배포 후 사람이 확인합니다.

★수동 NO-GO 규칙(R3-P0 D12 — 러너 동결 유지·사람 판정 보강): 아래 field_equals는 전부
로컬 결정론 데이터 검증이라 러너에서는 WARN이지만, 매뉴얼 응답(check 3~9 — 본권·별권 보존 검사 포함)의 field_equals
불일치는 infra 변동이 아니라 코드 회귀이므로 사람 판정에서 BLOCK으로 취급할 것.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN·매뉴얼 check는 사람 판정 BLOCK]
"""

_LAW_LINE = "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다."
_MANUAL_SOURCE_LINE = (
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)
_PROVISION_FOOTER = _LAW_LINE + "\n" + _MANUAL_SOURCE_LINE
_MANUAL_DISCLAIMER_LINE = (
    "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
    "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
)
_MAIN_NOTICE = "인용 매뉴얼: 26.7판 · 법령 시행일 2026-06 기준"
_B3_NOTICE = (
    "인용 자료: 「국가연구개발사업 제재처분 가이드라인」(국가연구개발혁신법 매뉴얼 별권 3) "
    "26.7판(판번은 게시 세트 기준) · 법령 기준일 원문 미표기"
)
# 별권 2 notice — edition-only 분기 재사용(D7)
_B2_NOTICE = (
    "인용 자료: 「국가연구개발사업 기술료 제도 매뉴얼」(국가연구개발혁신법 매뉴얼 별권 2) "
    "26.7판(판번은 게시 세트 기준) · 법령 기준일 원문 미표기"
)
_B2_FOOTER_4LINES = (
    _PROVISION_FOOTER + "\n" + _MANUAL_DISCLAIMER_LINE + "\n※ " + _B2_NOTICE
)
_MIXED_NOTICE_3 = _MAIN_NOTICE + " / " + _B3_NOTICE + " / " + _B2_NOTICE
_B2_CITATION_3_2 = "「국가연구개발사업 기술료 제도 매뉴얼」(26.7판) 제3장 2. 정부납부기술료 납부 기준, 인쇄 p.5"

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
        "name": "무회귀 — 규정 상세 footer 2줄(문면 무변·별권 2 도입 무영향)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀(보존 표면 ①) — 본권 절 문면 불변",
        "tool": "get_manual_section",
        "args": {"section_id": "3-13"},
        "asserts": [
            {"kind": "field_equals", "path": "section_title", "value": "간접비 사용용도 및 사용기준"},  # WARN
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _MAIN_NOTICE},     # WARN
            {"kind": "field_equals", "path": "manual_meta.manual_basis_date", "value": "2026-06"},  # WARN
        ],
    },
    {
        "name": "무회귀(보존 표면 ①) — 별권 3 절 문면 불변(b3-5-3 notice·기준일 null)",
        "tool": "get_manual_section",
        "args": {"section_id": "b3-5-3"},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _B3_NOTICE},       # WARN
            {"kind": "field_equals", "path": "manual_meta.manual_basis_date", "value": None},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "★신규 A — 별권 2 절 상세(b2-3-2 요율표 절) citation·notice·footer 4줄·병합 셀 고지",
        "tool": "get_manual_section",
        "args": {"section_id": "b2-3-2"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 신규
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation", "value": _B2_CITATION_3_2},           # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _B2_NOTICE},       # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.manual_basis_date", "value": None},  # WARN — 기준일 원문 미표기
            {"kind": "field_equals", "path": "manual_meta.standard_footer", "value": _B2_FOOTER_4LINES},  # WARN — 신규
        ],
    },
    {
        "name": "★신규 B — 별권 2 검색 도달('정부납부기술료 납부 기준' 제3장 절 최상위) + 3소스 스캔",
        "tool": "search_manual",
        "args": {"query": "정부납부기술료 납부 기준"},
        "asserts": [
            # returned_not_below는 search_provision의 results 키 전용(러너 동결) — 로컬 결정론
            # 데이터인 search_manual은 field_equals로 검증(v0.31.0·v0.32.0 spec과 동일 사상).
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "b2-3-1"},        # WARN — 신규(장 제목 tier)
            {"kind": "field_equals", "path": "matches.0.source", "value": "b2"},                # WARN — 신규
            {"kind": "field_equals", "path": "scanned_sections", "value": 81},                  # WARN — 본권 43+별권3 23+별권2 15
        ],
    },
    {
        "name": "★신규 C — 3소스 혼합('기술료') 본권 우선 정렬 + 병기 notice 2회 + 소스별 기준일 격리",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "2-6"},           # WARN — 본권 우선 유지
            {"kind": "field_equals", "path": "matches.0.source", "value": "main"},              # WARN
            {"kind": "field_equals", "path": "returned_by_source.b2", "value": 8},              # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _MIXED_NOTICE_3},   # WARN — 3원 병기 완성형
            {"kind": "field_equals", "path": "manual_meta.sources.b2.manual_basis_date", "value": None},  # WARN — 전이 차단
            {"kind": "field_equals", "path": "manual_meta.sources.main.manual_basis_date", "value": "2026-06"},  # WARN
        ],
    },
    {
        "name": "★신규 D — 목차 오기 표기('운영체계') known-variant 검색 도달(P1 데이터-only)",
        "tool": "search_manual",
        "args": {"query": "기술료 운영체계"},
        "asserts": [
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "b2-2-1"},        # WARN — 신규
            {"kind": "field_equals", "path": "returned", "value": 1},                           # WARN
        ],
    },
    {
        "name": "★신규 E — 무매치 질의(3소스 0건) 스캔 총수·0건 footer 2줄(허위 인용 고지 차단)",
        "tool": "search_manual",
        "args": {"query": "존재하지않는키워드검증용문자열"},
        "asserts": [
            {"kind": "field_equals", "path": "returned", "value": 0},                           # WARN
            {"kind": "field_equals", "path": "scanned_sections", "value": 81},                  # WARN — 신규
            {"kind": "field_equals", "path": "total_matched_by_source.b2", "value": 0},         # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.standard_footer", "value": _PROVISION_FOOTER},  # WARN — 2줄
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.33.0 = 기술료 구체값의 시행령 교차 확인·구판 용어 정정.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 요율표(b2-3-2) 구체값의 시행령 교차 확인 유도",
        "probe_prompt": "중견기업이 연구개발성과를 직접 실시해서 수익이 났을 때 정부납부기술료를 얼마나 내야 하는지, "
                        "근거와 함께 알려줘.",
        "expect_behavior": "별권 2(b2-3-2)의 요율표(직접 실시·중견기업 5%·상한 정부지원연구개발비의 20%)에 도달하되, "
                           "규범성 안내에 따라 시행령 제38조·제39조 원문(get_provision_detail)을 교차 확인하는지. "
                           "분류(제3자/직접 실시) 병합 셀 고지를 반영해 행 귀속을 원문 기준으로 확인하는지. "
                           "하단 안내 4줄에 '법령 기준일 원문 미표기'가 유지되는지.",
    },
    {
        "category": "★표적 — 구판 용어의 현행 정정(law_priority_extra 3문장째 실효)",
        "probe_prompt": "기술료등납부의무기관이 뭔지, 지금도 그 용어가 맞는지 매뉴얼 해설과 함께 알려줘.",
        "expect_behavior": "별권 2 해설(구용어 '기술료등납부의무기관')을 전달하면서, 규범성 안내의 구판 용어 문장을 "
                           "반영해 현행 시행령(2026-07-28 시행)에서는 '정부납부기술료납부의무기관'으로 변경되었음을 "
                           "시행령 제38조 원문으로 확인·안내하는지(매뉴얼 원문을 현행 용어로 날조 변경하지 않는지).",
    },
    {
        "category": "★표적 — 부록 분수식 고지 소비(관계 단정 여부)",
        "probe_prompt": "제품 단위 매출액을 산정하기 어려울 때 기술기여도를 어떻게 계산하는지 산식을 정확히 알려줘.",
        "expect_behavior": "별권 2 부록(b2-ref-1)의 산정 예시에 도달하되, 분수식이 평면 직렬화되어 분자·분모 관계가 "
                           "텍스트에 없다는 warnings를 반영하는지 — 산식 구조를 텍스트 순서만으로 단정하지 않고 "
                           "인쇄쪽 원문 확인을 안내하거나 관계를 보수적으로 서술하는지.",
    },
    {
        "category": "관찰 — 3소스 혼합 답변의 자료 구분·병기 notice",
        "probe_prompt": "기술료를 미납하면 어떤 제재를 받는지 매뉴얼 해설과 함께 정리해줘.",
        "expect_behavior": "본권·별권 3(제재 기준)·별권 2(기술료 제도)를 함께 인용할 때 세 자료를 구분 표기하는지. "
                           "별권 2·별권 3에 본권 기준일(2026.6월)을 잘못 붙이지 않는지. 하단 안내가 병기 notice "
                           "1블록으로 나오는지(중복 부착 0).",
    },
]
