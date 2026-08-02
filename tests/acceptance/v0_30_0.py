"""v0.30.0 배포 전 LIVE acceptance spec — 「출처·원문 확인 경로 정비」.

읽는 법(비프로그래머용): 이번 v0.30.0은 답변 하단 표준 안내를 두 갈래로 정비한 릴리스입니다.
① 하단 안내 첫 줄을 맥락 중립 문면("관련 규정 원문")으로 교체 — v0.29.0 배포 후 관측에서
법률만 다룬 답변이 "행정규칙" 단어를 2/2 삭제한 결함의 원인 제거. ② 매뉴얼 원문 안내
(KISTEP 홈페이지·URL/판번 미포함) 고정 2번째 줄을 전 footer 경로에 신설 + 매뉴얼 응답
manual_meta에 임베드 판 게시물 URL(source_url)을 기계 가독 출처로 additive 제공.
규정 상세 footer = 2줄 / 매뉴얼 인용 footer = 4줄이며 처음 두 줄은 동일 문자열(호스트 dedup).
Level A(자동)는 기존 무회귀 + 신규 문면·필드의 결정론 확인. 개선의 핵심(호스트가 새 문면을
축약 없이 부착하는가)은 Level B로 배포 후 사람이 확인합니다.

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
_SOURCE_URL = "https://www.kistep.re.kr/board.es?mid=a10301000000&bid=0003&act=view&list_no=94702"

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
        "name": "★신규 A — 조문(JO) footer 2줄 신문면 글자 단위 일치(혁신법 제13조)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN — 신규
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 무회귀
        ],
    },
    {
        "name": "★신규 B — 문서레벨(admrul 사용기준) footer 2줄 신문면",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278740"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN — 신규
        ],
    },
    {
        "name": "★신규 C — 별표(BP) oversized_pointer에도 footer 2줄 + tier 무회귀(law:285767:BP0002)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 무회귀
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN — 무회귀
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN — 신규
        ],
    },
    {
        "name": "★신규 D — 매뉴얼 상세 footer 4줄(신문면 승계) + source_url + citation 무회귀(3-9)",
        "tool": "get_manual_section",
        "args": {"section_id": "3-9"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "manual_meta.source_url", "value": _SOURCE_URL},  # WARN — 신규
            {"kind": "field_equals", "path": "manual_meta.standard_footer",
             "value": (_PROVISION_FOOTER + "\n"
                       "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
                       "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다.\n"
                       "※ 인용 매뉴얼: 26.4판 · 법령 시행일 2026-03 기준")},                   # WARN — 신규 4줄
            {"kind": "field_equals", "path": "citation",
             "value": "「국가연구개발혁신법 매뉴얼(본권)」(26.4판) 제3장 제9절 보안수당 사용용도 및 사용기준, 인쇄 p.243~244"},  # WARN — 무회귀
        ],
    },
    {
        "name": "★신규 E — 매뉴얼 포인터(2-3)는 미인용형 2줄(허위 고지 차단 무회귀)",
        "tool": "get_manual_section",
        "args": {"section_id": "2-3"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — 무회귀
            {"kind": "field_equals", "path": "manual_meta.standard_footer", "value": _PROVISION_FOOTER},  # WARN — 신규
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.30.0 = 신문면의 글자 단위 유지율(축약 재현 여부) 재측정.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 법률-only 답변에서 중립 문면 무축약 유지(직전 2/2 축약 축의 직접 재측정)",
        "probe_prompt": "국가연구개발혁신법 제13조가 정한 사항을 법률 조문 원문을 근거로 설명해 주세요.",
        "expect_behavior": "규정 도구로 조문 verbatim 제공 후 하단에 2줄 footer가 그대로 부착되는지. "
                           "★핵심 관측: 첫 줄 '관련 규정 원문'이 글자 단위로 유지되는지(구문면에서는 이 프로브에서 "
                           "'행정규칙'이 2/2 삭제됨 — 중립화 실효의 직접 재측정). 2번째 줄(KISTEP 안내)의 "
                           "부착·삭제 여부도 별도 기록(법령-only 맥락 삭제 유인 관측 항목).",
    },
    {
        "category": "★표적 — 매뉴얼 인용 답변 4줄 부착 + 중복 0(단일 분기 무회귀)",
        "probe_prompt": "혁신법 매뉴얼에서 학생인건비 계상 기준 해설을 찾아 인쇄쪽과 함께 알려줘.",
        "expect_behavior": "매뉴얼 도구 호출 후 4줄 standard_footer가 그대로 1회 부착되는지(규정 2줄을 이어 붙이는 "
                           "중복 없음 — 처음 두 줄 동일 문자열 dedup). 인쇄쪽 citation 무회귀.",
    },
    {
        "category": "관찰 — 매뉴얼 무관 규정(국방 등) 답변에서 KISTEP 줄 거동",
        "probe_prompt": "방위사업청이 발주한 국방 R&D 과제는 어떤 법령 체계를 따르는지 근거 규정을 확인해서 설명해줘.",
        "expect_behavior": "국방 라우팅 가드 무회귀(혁신법 전면 적용·전면 배제 단정 없음). ★관측: 매뉴얼과 무관한 "
                           "규정 답변에서 2번째 줄(KISTEP 매뉴얼 안내)이 유지되는지 삭제되는지 — 일반 안내형 문면의 "
                           "생존율 기록(위해 없음·관측만, 계획 문서 §8-3 잔여 관측 항목).",
    },
]
