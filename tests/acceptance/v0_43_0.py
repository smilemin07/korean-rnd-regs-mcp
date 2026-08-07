"""v0.43.0 배포 전 LIVE acceptance spec — 「국가 R&D 연구비 부적정집행 사례집」(KAIA·25.5) 수록.

읽는 법(비프로그래머용): 이번 v0.43.0은 KAIA(국토교통과학기술진흥원) 발간 연구비 사례집을
매뉴얼 트랙 일곱 번째 소스로 수록합니다(id 계열 case-장-절·contract 0.32.0·입력 스키마 무변 →
재연결 불요). 기존 매뉴얼 데이터 6종·규정 트랙 무접촉이며, 함께 요청됐던 「연구자를 위한
국가연구개발사업 제재제도 설명서」(25.2)는 PDF 텍스트 레이어 부재로 수록 보류입니다.
매뉴얼 도구는 네트워크가 없으므로(로컬 JSON) Level A는 규정 트랙 무회귀 + 사례집 결정론
표면을 함께 봅니다. 핵심 결정론 잠금은 pytest(test_manual_case_tools.py 27건 + 128조합 전수)가
담당하며, field_equals는 러너 동결 규약상 WARN(사람 판정 참고)입니다.
★러너 규약 한계(동결): returned_not_below는 응답의 `results` 키(search_provision 전용)만 세므로
search_manual의 반환 수는 field_equals(path="returned_by_source.case" 등 결정론 값)로만 본다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(사례집 추가의 규정 트랙 무영향)",
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
        "name": "★신규 A — case-2-2 상세: 2레벨 id·원문 표기 보존 citation(장 생략·Ⅱ. 라벨)",
        "tool": "get_manual_section",
        "args": {"section_id": "case-2-2"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가 R&D 연구비 부적정집행 사례집」(25.5판) "
                      "Ⅱ. 부적정집행 사례 02 학생인건비, 인쇄 p.24~28"},                        # WARN
        ],
    },
    {
        "name": "★신규 B — case-4-1(Ⅳ장 절차 도식): 본문 제공 + citation(도식 structure_notice는 pytest 전담)",
        "tool": "get_manual_section",
        "args": {"section_id": "case-4-1"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가 R&D 연구비 부적정집행 사례집」(25.5판) "
                      "Ⅳ. 상시·연차점검 / 정산 절차, 인쇄 p.94~95"},                            # WARN
        ],
    },
    {
        "name": "★신규 C — 병합 검색 결정론: case 단독 매치 질의(로컬 데이터·비LIVE)",
        "tool": "search_manual",
        "args": {"query": "부적정집행 사례"},
        "asserts": [
            {"kind": "field_equals", "path": "returned_by_source.case", "value": 10},            # WARN
            {"kind": "field_equals", "path": "scanned_sections", "value": 146},                  # WARN
        ],
    },
    {
        "name": "무회귀 — 별권 4 b4-5 citation 불변(직전 매뉴얼 릴리스 보존 표면)",
        "tool": "get_manual_section",
        "args": {"section_id": "b4-5"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(26.7판) "
                      "Ⅴ. 통합 연구시설･장비비의 계상･지급･적립, 인쇄 p.14~17"},               # WARN
        ],
    },
    {
        "name": "무회귀 — 과제평가 표준지침 eval-1-1 citation 불변(비시리즈 소스 보존 표면)",
        "tool": "get_manual_section",
        "args": {"section_id": "eval-1-1"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가연구개발 과제평가 표준지침」(25.12판) 제1장 1. 법적근거, 인쇄 p.1"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 규정 상세 verbatim(규정 트랙 무접촉 확인)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.43.0 = 사례집 자연 라우팅·KAIA 프로세스
# 사실 라벨 실효·'부적정집행'≠제재처분 구분·기존 트랙 무회귀가 관측 표적.
# ★프로브 설계 주의([[eval-probe-contamination]]): 맥락 없는 질문은 호스트 대화 메모리가
# 오염시킴 — 각 프로브는 자립형 문안이며, 관측 필드(citation·footer)를 문안에서 명시 요구.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 사례집 자연 라우팅 + citation·footer(KAIA 문면) 표시",
        "probe_prompt": "국가 R&D에서 학생인건비를 교수(연구책임자)가 공동관리하면 어떤 문제가 되는지, "
                        "실제 부적정집행 사례집에 실린 사례가 있으면 출처(자료명·인쇄쪽)와 함께 알려줘.",
        "expect_behavior": "search_manual→get_manual_section 경유 case-2-2(학생인건비) 도달·citation"
                           "(「국가 R&D 연구비 부적정집행 사례집」(25.5판) …, 인쇄쪽) 표기·footer에 KAIA 발간 "
                           "사례집 문면(처분·정산 판정 아님·법령 우선)이 표시되는지. 사례를 개별 사안에 대한 "
                           "확정 판정처럼 단정하면 FAIL.",
    },
    {
        "category": "★표적 — Ⅳ장 KAIA 프로세스 사실 라벨 실효(law_priority_extra 소비)",
        "probe_prompt": "국가연구개발과제 연구비 연차점검과 정산은 어떤 절차로 진행되는지 부적정집행 "
                        "사례집 기준으로 알려줘. 우리 과제는 산업통상자원부 소관이야.",
        "expect_behavior": "case-4-1 도달 후 Ⅳ장 절차(Ez-baro·위탁정산기관·일정)가 KAIA 국토교통R&D 프로세스 "
                           "기준이라는 사실 라벨이 소비되어, 산업부 과제는 해당 전문기관 절차 확인을 안내하는지"
                           "(규범성 사실 문장 실효 관측). KAIA 절차를 범부처 공통 절차로 단정하면 FAIL.",
    },
    {
        "category": "★표적 — '부적정집행'≠제재처분 구분 + 별권 3 위계",
        "probe_prompt": "연구비를 사용용도 외로 집행해서 정산에서 불인정된 경우, 이것이 곧바로 제재처분 "
                        "대상이 되는지 사례집과 규정을 근거로 검토해줘.",
        "expect_behavior": "사례집(case-2-N)의 불인정·회수 사례와 제재처분(혁신법 제32조·시행령·별권 3)을 "
                           "구분하고, 사용용도·사용기준 모두 위반 시의 제재 가능성은 법령 원문으로 확인하는지"
                           "(law_priority_extra 2항 소비). 불인정=제재처분으로 단정하면 FAIL.",
    },
    {
        "category": "무회귀 — 학생인건비(별권 1) 트랙 분리 유지",
        "probe_prompt": "학생인건비통합관리 제도 매뉴얼에서 통합관리계정 이자 처리를 어떻게 안내하는지 알려줘.",
        "expect_behavior": "b1-3-6 도달·citation(인쇄 p.32)·footer 4줄이 기존과 동일하고, 같은 '학생인건비' "
                           "용어의 사례집(case-2-2)으로 오라우팅하지 않는지(명시 자료 지정 시 트랙 분리).",
    },
]
