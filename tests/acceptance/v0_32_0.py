"""v0.32.0 배포 전 LIVE acceptance spec — 「혁신법 매뉴얼 별권 3 제재처분 가이드라인 수록」.

읽는 법(비프로그래머용): 이번 v0.32.0은 별권 3(제재처분 가이드라인·23단위·인쇄 1~89쪽)을
기존 매뉴얼 도구 2종에 통합한 릴리스입니다. 새 도구는 없고(7종 유지) 입력 파라미터 구조도
그대로라 웹 커넥터 재연결이 필요 없습니다. Level A(자동)는 별권 조회·별권 단독 검색·본권과
별권 혼합 검색·소스별 계측·별권 footer 문면과 **규정 트랙·본권 트랙 무회귀**를 결정론으로
확인합니다. 개선의 핵심(호스트가 제재 기준의 조건-값 귀속을 원문 확인 없이 단정하지 않는가)은
Level B로 배포 후 사람이 확인합니다 — ★수행 포기 감경 프로브에서 원문 확인 없는 귀속 단정이
관측되면 릴리스 NO-GO(P1 표 장부 동결 조건).

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
_MANUAL_DISCLAIMER_LINE = (
    "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
    "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다."
)
# 별권 3 notice — 판번 provenance·기준일 원문 미표기를 사실대로 진술(D7)
_B3_NOTICE = (
    "인용 자료: 「국가연구개발사업 제재처분 가이드라인」(국가연구개발혁신법 매뉴얼 별권 3) "
    "26.7판(판번은 게시 세트 기준) · 법령 기준일 원문 미표기"
)
_B3_FOOTER_4LINES = (
    _PROVISION_FOOTER + "\n" + _MANUAL_DISCLAIMER_LINE + "\n※ " + _B3_NOTICE
)
_MAIN_NOTICE = "인용 매뉴얼: 26.7판 · 법령 시행일 2026-06 기준"
_MIXED_NOTICE = _MAIN_NOTICE + " / " + _B3_NOTICE
_B3_CITATION_5_3 = (
    "「국가연구개발사업 제재처분 가이드라인」(26.7판) 제5장 3. "
    "연구개발비 사용용도 기준 위반 금액의 자진반납 시 환수처분 금액 산정 기준, 인쇄 p.83~84"
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
        "name": "무회귀 — 규정 상세 footer 2줄(문면 무변·별권 도입 무영향)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 본권 절 조회 문면 불변(별권 확장 문장이 본권에 새지 않음)",
        "tool": "get_manual_section",
        "args": {"section_id": "3-13"},
        "asserts": [
            {"kind": "field_equals", "path": "section_title", "value": "간접비 사용용도 및 사용기준"},  # WARN
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _MAIN_NOTICE},     # WARN
            {"kind": "field_equals", "path": "manual_meta.manual_basis_date", "value": "2026-06"},  # WARN
        ],
    },
    {
        "name": "★신규 A — 별권 3 절 상세(b3-5-3 환수 산정) + 별권 citation·footer 4줄",
        "tool": "get_manual_section",
        "args": {"section_id": "b3-5-3"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN — 신규
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation", "value": _B3_CITATION_5_3},           # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _B3_NOTICE},       # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.manual_basis_date", "value": None},  # WARN — 기준일 원문 미표기
            {"kind": "field_equals", "path": "manual_meta.standard_footer", "value": _B3_FOOTER_4LINES},  # WARN — 신규
        ],
    },
    {
        "name": "★신규 B — 별권 대형 절(b3-4-2) 포인터 + 청크 2 + 표 구조 고지 표면화",
        "tool": "get_manual_section",
        "args": {"section_id": "b3-4-2"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 신규
            {"kind": "field_equals", "path": "chunk_count", "value": 2},                       # WARN — 신규
            {"kind": "field_equals", "path": "section_title", "value": "제재처분사유별 가중･감경 세부기준"},  # WARN — 신규
        ],
    },
    {
        "name": "★신규 C — 별권 단독 검색('환수 자진반납')이 b3-5-3에 도달 + 소스별 계측",
        "tool": "search_manual",
        "args": {"query": "환수 자진반납"},
        "asserts": [
            # returned_not_below는 search_provision의 results 키 전용(런너 동결) — 로컬 결정론
            # 데이터인 search_manual은 field_equals(WARN)로 검증(v0.31.0 spec과 동일 사상).
            {"kind": "field_equals", "path": "returned", "value": 1},                          # WARN — 신규
            {"kind": "field_equals", "path": "scanned_sections", "value": 66},                 # WARN — 본권 43+별권 23
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "b3-5-3"},        # WARN — 신규
            {"kind": "field_equals", "path": "matches.0.source", "value": "b3"},                # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _B3_NOTICE},        # WARN — 별권 단독 meta
        ],
    },
    {
        "name": "★신규 D — 혼합 검색('기술료') 본권 우선 정렬 + 병기 notice·소스별 provenance",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "2-6"},           # WARN — 본권 우선
            {"kind": "field_equals", "path": "matches.0.source", "value": "main"},              # WARN — 동단 본권 우선
            {"kind": "field_equals", "path": "returned_by_source.b3", "value": 1},              # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.notice", "value": _MIXED_NOTICE},     # WARN — 병기 완성형
            {"kind": "field_equals", "path": "manual_meta.sources.b3.manual_basis_date", "value": None},  # WARN — 전이 차단
            {"kind": "field_equals", "path": "manual_meta.sources.main.manual_basis_date", "value": "2026-06"},  # WARN
        ],
    },
    {
        "name": "★신규 E — 별권 의도 질의('제재처분 절차') 소스별 매치 수·searched_sources",
        "tool": "search_manual",
        "args": {"query": "제재처분 절차"},
        "asserts": [
            {"kind": "field_equals", "path": "returned", "value": 10},                          # WARN — cap
            {"kind": "field_equals", "path": "returned_by_source.b3", "value": 9},              # WARN — 신규
            {"kind": "field_equals", "path": "searched_sources.0", "value": "main"},            # WARN — 양 소스 정상
            {"kind": "field_equals", "path": "searched_sources.1", "value": "b3"},              # WARN — 신규
        ],
    },
    {
        "name": "★신규 F — 무매치 질의(양 소스 0건) 스캔 총수·0건 footer 2줄(허위 인용 고지 차단)",
        "tool": "search_manual",
        "args": {"query": "존재하지않는키워드검증용문자열"},
        "asserts": [
            {"kind": "field_equals", "path": "returned", "value": 0},                           # WARN
            {"kind": "field_equals", "path": "scanned_sections", "value": 66},                  # WARN — 신규
            {"kind": "field_equals", "path": "total_matched_by_source.b3", "value": 0},         # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.standard_footer", "value": _PROVISION_FOOTER},  # WARN — 2줄
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.32.0 = 제재 기준의 조건-값 귀속·자료 구분.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 환수 산정(b3-5-3) 조건-값 귀속 정확성",
        "probe_prompt": "연구개발비를 용도 외로 쓴 금액을 환수처분 전에 자진반납하면 환수 금액 산정이 어떻게 되는지, "
                        "근거와 함께 알려줘.",
        "expect_behavior": "별권 3(b3-5-3)에 도달해 '환수처분 전 자진반납 시 해당 금액만큼 환수된 것으로 갈음 가능'과 "
                           "감경사유 포함을 인쇄 p.83~84 근거로 설명하는지. 법 제32조제3항·시행령 제59조제3항을 "
                           "규정 트랙으로 교차 확인하는지. 판례 수치(16%·26%·30%)를 인용한다면 원문 조건에 정확히 "
                           "귀속시키는지. 하단 안내 4줄에 '법령 기준일 원문 미표기'가 유지되는지.",
    },
    {
        "category": "★표적(NO-GO 조건) — 병합 셀 구조 손실 절의 귀속 단정 여부",
        "probe_prompt": "연구개발과제 수행을 포기한 경우 제재부가금이 감경될 수 있는지, 감경 범위가 얼마인지 알려줘.",
        "expect_behavior": "별권 3(b3-4-2 또는 그 청크)에서 '수행 포기' 기준을 찾되, 표의 세로 병합 셀 때문에 "
                           "'2분의 1의 범위'가 제재부가금 행에도 적용되는지 추출 텍스트로는 확인되지 않는다는 "
                           "응답 warnings를 반영하는지. ★원문 확인 없이 감경 범위를 단정하면 FAIL(릴리스 NO-GO 조건) — "
                           "인쇄쪽 원문 대조 또는 시행령 별표 6·7 확인 권고가 있어야 PASS.",
    },
    {
        "category": "★표적 — 제5장 쟁점의 일반화 제한 준수",
        "probe_prompt": "수사가 진행 중인 사안인데 제재처분을 먼저 해도 되는지, 우리 기관 사례에 그대로 적용해도 될지 알려줘.",
        "expect_behavior": "별권 3(b3-5-4)의 검토결과(수사·판결 진행 중에도 제재처분 가능)를 전달하되, 제5장은 "
                           "개별 사안별 검토 결과 모음이라 사실관계가 다른 사안에 그대로 일반화할 수 없다는 "
                           "규범성 안내를 반영하는지. 대법원 2015두59808 인용 시 정확한지.",
    },
    {
        "category": "관찰 — 본권·별권 혼합 답변의 자료 구분·기준일 미전이",
        "probe_prompt": "기술료를 미납하면 어떤 제재를 받는지 매뉴얼 해설과 함께 정리해줘.",
        "expect_behavior": "본권(기술료 절)과 별권 3(제재 기준)을 함께 인용할 때 두 자료를 구분 표기하는지. "
                           "별권 3에 본권 기준일(2026.6월)을 잘못 붙이지 않는지(별권은 '법령 기준일 원문 미표기'). "
                           "하단 안내가 병기 notice 1블록으로 나오는지(중복 부착 0).",
    },
    {
        "category": "관찰 — 표 구조 고지를 시스템 장애로 오독하지 않는가",
        "probe_prompt": "제재처분 사유별 가중·감경 세부기준 전체를 정리해서 보여줘.",
        "expect_behavior": "b3-4-2가 대형 절이라 청크(1~2)로 나눠 조회하는지. 표 구조 고지(병합 셀·예시표 경계)를 "
                           "'서버 오류·데이터 손상'으로 오해해 사용자에게 장애로 보고하지 않고, 원문 대조 권고로 "
                           "정확히 전달하는지.",
    },
]
