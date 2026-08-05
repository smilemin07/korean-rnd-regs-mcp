"""v0.39.0 배포 전 LIVE acceptance spec — 「R5: 혁신법 매뉴얼 별권 4 수록」.

읽는 법(비프로그래머용): 이번 v0.39.0은 혁신법 매뉴얼 별권 4 「연구시설･장비비 통합관리제
운영･관리 매뉴얼」(26.7 게시 세트)을 매뉴얼 트랙 여섯 번째 소스로 수록합니다(시리즈 완결).
장 없는 평면 편제라 최초의 단일 레벨 id(b4-0~b4-9·b4-ref-1)를 사용하고, 기존 매뉴얼 데이터
5종 byte 불변·입력 스키마 무변(contract 0.29.0 → 재연결 불요)입니다. 동반 소항목으로 매뉴얼
장애 안내 문면 5곳을 격리 사실 문면으로 정비했습니다(오류 경로 한정 — 정상 응답 무변).
매뉴얼 도구는 네트워크가 없으므로(로컬 JSON) Level A는 규정 트랙 무회귀 + 매뉴얼 결정론
표면을 함께 봅니다. 핵심 결정론 잠금은 pytest(test_manual_b4_tools.py 26건 + 64조합 전수)가
담당하며, field_equals는 러너 동결 규약상 WARN(사람 판정 참고)입니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(매뉴얼 소스 추가의 규정 트랙 무영향)",
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
        "name": "★신규 A — b4-5 상세: 단일 레벨 id·장 생략 citation(로마숫자 label)",
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
        "name": "★신규 B — b4-ref-1(붙임 14.2k) 포인터 + 청크 2 표면(검색/상세 판정 차이 문서화 거동)",
        "tool": "get_manual_section",
        "args": {"section_id": "b4-ref-1"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN
            {"kind": "field_equals", "path": "chunk_count", "value": 2},                       # WARN
        ],
    },
    {
        "name": "무회귀 — 과제평가 표준지침 eval-1-1 citation 불변(직전 릴리스 보존 표면)",
        "tool": "get_manual_section",
        "args": {"section_id": "eval-1-1"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가연구개발 과제평가 표준지침」(25.12판) 제1장 1. 법적근거, 인쇄 p.1"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 규정 상세 footer·verbatim(규정 트랙 무접촉 확인)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.39.0 = 별권 4 자연 라우팅·붙임 구판 발췌
# 사실 라벨(law_priority_extra) 실효·기존 트랙 무회귀가 관측 표적.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 별권 4 자연 라우팅 + 단일 레벨 citation",
        "probe_prompt": "연구시설·장비비 통합관리제에서 통합관리계정 적립 한도는 어떻게 정하는 것으로 "
                        "매뉴얼이 안내하는지, 출처와 함께 알려줘.",
        "expect_behavior": "search_manual→get_manual_section 경유 b4-4/b4-5 도달·citation(「연구시설･장비비 "
                           "통합관리제 운영･관리 매뉴얼」(26.7판) Ⅳ./Ⅴ. …, 인쇄쪽) 표기·footer 4줄(기본 문면)·"
                           "구체값은 사용 기준 제7장(제100조~제111조) 현행 원문 교차 확인 안내가 있는지. "
                           "매뉴얼 해설을 법령 조문처럼 단정하면 FAIL.",
    },
    {
        "category": "★표적 — 붙임 구판 발췌 사실 라벨 실효(law_priority_extra 소비)",
        "probe_prompt": "연구시설·장비비 통합관리제 운영·관리 매뉴얼 붙임에 실린 연구개발비 사용 기준 조문을 "
                        "그대로 인용해서 통합관리기관 지정 요건을 알려줘.",
        "expect_behavior": "붙임(b4-ref-1) 발췌가 고시 제2023-49호(2023.12.28.) 스냅샷이라는 안내가 소비되어 "
                           "현행 원문(rnd_funding_standard 제100조) 교차 확인으로 이어지는지(규범성 사실 문장 "
                           "실효의 5번째 관측 축). 붙임 발췌를 현행 조문으로 단정 인용하면 FAIL.",
    },
    {
        "category": "무회귀 — 학생인건비(별권 1) 트랙 분리 유지",
        "probe_prompt": "학생인건비통합관리 제도 매뉴얼에서 통합관리계정 이자 처리를 어떻게 안내하는지 알려줘.",
        "expect_behavior": "b1-3-6 도달·citation(인쇄 p.32)·footer 4줄이 기존과 동일하고, 같은 '통합관리' 용어의 "
                           "별권 4(시설·장비비)로 오라우팅하지 않는지(두 통합관리제 트랙 분리).",
    },
]
