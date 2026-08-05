"""v0.37.0 배포 전 LIVE acceptance spec — 「resolver 안전성 정비: 미래 시행 행 필터·개정 예정 고지·fallback 발동 고지」.

읽는 법(비프로그래머용): 이번 v0.37.0은 최신 판본 확인(search-first resolve)이 시행일이 아직
오지 않은 판본을 현행처럼 선택하던 결함을 바로잡습니다(2026-08-06 라이브 실측 — 정보처리기준이
미시행 고시 제2026-47호 본문을 "개정 반영"으로 반환). 이제 시행일 ≤ 오늘(KST) 행만 현행으로
선택되고, 예정 판본이 있으면 upcoming_revision, 확인 실패 시 resolve_fallback_notice가 응답에
포함됩니다(응답 additive 2종·입력 스키마 무변·contract 0.27.0 → 웹 커넥터 재연결 불요).

★날짜 의존 주의: 첫 번째 신규 체크(정보처리기준)는 2026-08-20 시행 도래 **전**에만 유효합니다.
그 후 실행하면 resolve가 신 판본을 정당하게 선택하여 field_equals가 어긋납니다(WARN 클래스라
차단은 없음) — 08-20 이후는 해당 체크 결과를 무시하고 manifest 갱신 릴리스로 넘어가십시오.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

_LAW_LINE = "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다."
_MANUAL_SOURCE_LINE = (
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)
_PROVISION_FOOTER = _LAW_LINE + "\n" + _MANUAL_SOURCE_LINE

# 개정 예정 고지 완성형(2026-08-20 도래 전 정보처리기준 기대값 — 문구는 main._resolve_status_fields 잠금과 동일)
_UPCOMING_INFO_PROCESSING = (
    "개정 예정: 2026-08-20 시행 예정인 새 판본(문서 ID 2100000283100)이 공포되어 있습니다. "
    "본 응답은 현행 시행본 기준이며, 시행일 도래 후에는 새 판본 기준으로 재확인이 필요합니다."
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(resolver 필터의 검색 무회귀)",
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
        "name": "★신규 A — 정보처리기준 doc-level: 미시행 판본 선택 차단(현행 2021-01-01 유지) + upcoming_revision 발화 (★08-20 전 한정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000195842"},
        "asserts": [
            {"kind": "field_equals", "path": "effective_date", "value": "2021-01-01"},        # WARN — ★핵심: 미시행 2026-08-20이 아니어야 함
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},        # WARN — 미시행 판본을 '개정 반영'으로 표기하지 않음
            {"kind": "field_equals", "path": "upcoming_revision", "value": _UPCOMING_INFO_PROCESSING},  # WARN — 예정 고지 완성형
            {"kind": "field_equals", "path": "resolve_fallback_notice", "value": "<missing>"},  # WARN — 예정 존재 ≠ 확인 실패
        ],
    },
    {
        "name": "★신규 B — 현행 정합 규정(시행령 288335): 상태 고지 2종 미발화(additive 무영향)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288335"},
        "asserts": [
            {"kind": "field_equals", "path": "effective_date", "value": "2026-07-28"},        # WARN — v0.36.0 정합 유지
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},        # WARN
            {"kind": "field_equals", "path": "upcoming_revision", "value": "<missing>"},      # WARN — 예정 판본 없으면 미발화
            {"kind": "field_equals", "path": "resolve_fallback_notice", "value": "<missing>"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 규정 상세 footer 2줄 + 조문 verbatim(혁신법 본법 경로 불변)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 매뉴얼 트랙 완전 무변(별권 1 b1-3-6 citation 글자 단위 불변)",
        "tool": "get_manual_section",
        "args": {"section_id": "b1-3-6"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「학생인건비통합관리 제도 매뉴얼」(26.7판) 제3장 6. 학생인건비 이자 처리, 인쇄 p.32"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.37.0 = 미시행 판본 차단·개정 예정 고지의 호스트
# 소비가 관측 표적. ★08-20 전에 관측해야 표적 A가 유효(도래 후에는 신 판본 선택이 정답으로 바뀜).
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 정보처리기준: 미시행 본문 미제공 + 개정 예정 고지 표시 (★2026-08-20 전 한정)",
        "probe_prompt": "국가연구개발정보처리기준이 언제 시행된 규정인지, 그리고 최근 개정이 있는지 확인해서 알려줘.",
        "expect_behavior": "현행 시행일 2021-01-01 기준으로 답하고, upcoming_revision(2026-08-20 시행 예정 새 판본 "
                           "공포)을 사용자에게 전달하는지. 종전 결함(미시행 2026-08-20을 현행·'개정 반영'으로 단정)이 "
                           "재현되지 않는지. 미시행 본문 내용을 현행 기준으로 단정 인용하면 FAIL.",
    },
    {
        "category": "무회귀 — 광역 검색 + 현행 정합 규정 조회(고지 미발화·기존 표시 불변)",
        "probe_prompt": "국가연구개발혁신법 시행령에서 연구개발성과 기탁 절차를 조문 근거와 함께 알려줘.",
        "expect_behavior": "제35조의2 도달·verbatim 인용이 v0.36.0 eval과 동일 유지. upcoming_revision 등 신규 필드가 "
                           "발화 조건 밖에서 나타나거나 허위 예정 고지가 붙지 않는지.",
    },
    {
        "category": "무회귀 — 매뉴얼 트랙(별권 1) citation·footer 유지",
        "probe_prompt": "학생인건비통합관리 제도 매뉴얼에서 통합관리계정 이자 처리를 어떻게 안내하는지 알려줘.",
        "expect_behavior": "b1-3-6 도달·citation(인쇄 p.32)·footer 4줄이 유지되는지(resolver 변경은 매뉴얼 트랙 "
                           "무접촉 — 회귀 0 확인용).",
    },
]
