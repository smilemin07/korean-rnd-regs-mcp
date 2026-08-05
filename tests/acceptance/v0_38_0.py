"""v0.38.0 배포 전 LIVE acceptance spec — 「국가연구개발 과제평가 표준지침(25.12) 수록」.

읽는 법(비프로그래머용): 이번 v0.38.0은 과제평가 표준지침(과기정통부·연구성과평가법 제13조 위임
범부처 표준지침·OpenAPI 미수록)을 매뉴얼 트랙 다섯 번째 소스(eval-·15단위)로 수록합니다.
기존 매뉴얼 데이터 4종 byte 불변·입력 스키마 무변(contract 0.28.0 → 재연결 불요).
매뉴얼 도구는 네트워크가 없으므로(로컬 JSON) Level A는 규정 트랙 무회귀 + 매뉴얼 결정론
표면을 함께 봅니다. 핵심 결정론 잠금은 pytest(test_manual_eval_tools.py 15건 + 32조합 전수)가
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
        "name": "★신규 A — eval-1-1 상세: citation·per-source footer 3번째 줄(지침 문면)",
        "tool": "get_manual_section",
        "args": {"section_id": "eval-1-1"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가연구개발 과제평가 표준지침」(25.12판) 제1장 1. 법적근거, 인쇄 p.1"},  # WARN
        ],
    },
    {
        "name": "★신규 B — eval-3-3(공통추진사항·18.6k) 포인터 + 청크 재조립 표면",
        "tool": "get_manual_section",
        "args": {"section_id": "eval-3-3"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN
            {"kind": "field_equals", "path": "chunk_count", "value": 2},                       # WARN
        ],
    },
    {
        "name": "무회귀 — 별권 1 b1-3-6 citation·기존 footer 문면 불변(보존 표면)",
        "tool": "get_manual_section",
        "args": {"section_id": "b1-3-6"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「학생인건비통합관리 제도 매뉴얼」(26.7판) 제3장 6. 학생인건비 이자 처리, 인쇄 p.32"},  # WARN
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

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.38.0 = 과제평가 표준지침의 자연 라우팅·문서 성격
# 고지(개정(안)·부처 지침 위계)·per-source footer가 관측 표적.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 과제평가 표준지침 자연 라우팅 + 문서 성격 고지",
        "probe_prompt": "국가연구개발 과제평가 표준지침에서 특별평가는 어떤 경우에 하는 것으로 안내하는지, "
                        "출처와 함께 알려줘.",
        "expect_behavior": "search_manual→get_manual_section 경유 eval-3-3 도달·citation(인쇄쪽) 표기·"
                           "footer 3번째 줄이 지침 문면('지침 해설 부분은 「국가연구개발 과제평가 표준지침」…')인지·"
                           "법령상 근거(혁신법 제12조~제16조) 교차 확인 또는 안내가 있는지. 지침 내용을 법령 조문처럼 "
                           "단정하면 FAIL.",
    },
    {
        "category": "★표적 — 부처 평가지침 위계 고지(law_priority_extra 실효)",
        "probe_prompt": "우리 기관 과제의 단계평가 기준을 국가연구개발 과제평가 표준지침만 보고 확정해도 되는지 알려줘.",
        "expect_behavior": "\"각 부처는 표준지침을 고려해 자체 평가지침을 마련하므로 구체 과제에는 소관 부처·전문기관의 "
                           "평가지침·공고·평가계획이 함께 적용\" 취지의 안내가 답변에 반영되는지(메타 사실 문장 소비 — "
                           "v0.33.0/v0.35.0 실증 패턴의 3번째 적용). 표준지침만으로 확정 가능하다고 단정하면 FAIL.",
    },
    {
        "category": "무회귀 — 별권 1 이자 처리(기존 매뉴얼 트랙 표시 불변)",
        "probe_prompt": "학생인건비통합관리 제도 매뉴얼에서 통합관리계정 이자 처리를 어떻게 안내하는지 알려줘.",
        "expect_behavior": "b1-3-6 도달·citation(인쇄 p.32)·footer 4줄(기존 문면 — '매뉴얼 해설 부분은 "
                           "「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다' 유지)이 v0.36.0 eval과 동일한지.",
    },
]
