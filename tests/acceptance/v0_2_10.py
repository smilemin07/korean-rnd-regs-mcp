"""v0.2.10 배포 전 LIVE acceptance spec — 「검색 fan-out 지연 관측성(B1)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts)은 코드가 아니라 데이터이며, 종류는 5가지로 고정:
  - fetched_ok      : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                              [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                                     [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드(예: timeout)가 0건.                                            [WARN — 차단 안 함]
  - latency_under   : 응답이 value초 미만.                                                          [WARN — 차단 안 함]
  - field_equals    : 응답의 특정 경로 값이 value와 같음.                                            [WARN — 차단 안 함]

★v0.2.10의 특수성 — 검증 무게중심이 자동(A)에서 수동(B, 로그 점검)으로 넘어간다:
  - v0.2.10 변경은 '서버 측 로그(stderr)' 추가뿐이며, search_provision/suggest_review_sources의
    검색·랭킹·fallback·응답 schema·동작을 전혀 바꾸지 않는다(응답 신규 필드 0·contract 0.6.0 유지).
    따라서 아래 Level A CHECKS는 '기능 증명'이 아니라 순수 '회귀 가드'다 — 광역 '연구개발비' 최상위·
    대형 규정 도달·recall이 v0.2.9 그대로인지(=로그 추가가 검색을 안 깼는지)만 확인한다.
  - 이 릴리스의 진짜 가치('fan-out 지연 관측 데이터')는 도구 *응답*이 아니라 *서버 로그*에 있어
    이 하니스의 5종 assert로는 관측 불가 → 배포 후 사람이 NAS 컨테이너 로그를 grep해 확인한다
    (LEVEL_B_PROMPTS = 로그 점검 절차, 게이트 판정 아님). 단위 가드는 tests/test_tools.py가 담당
    (요약 INFO·per-rule DEBUG·시크릿 미포함 결정론 검증).

새 버전 만들 때: 이 파일을 복사해 v0_2_11.py 등으로 두고 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

# 대형 규정(로그 추가가 도달·recall을 회귀시키지 말아야 할 것) — id는 rule_sets.yaml 기준
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "검색 불변 회귀 가드 — 광역 '연구개발비' 최상위·매몰 규정 생존(v0.2.9 동작 유지)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 5}]                       # recall net (block 후보)
            # ★관련도 advisory(WARN): 문서 제목이 '연구개발비'를 직접 가진 규정이 최상위 유지인지
            #   (로그 추가가 v0.2.8 정렬을 안 깼음을 실증; LIVE cold 변동 가능 → WARN).
            + [{"kind": "field_equals", "path": "results.0.rule_set_id", "value": "rnd_funding_standard"}]
        ),
    },
    {
        "name": "핀포인트 비회귀 — '기술료'(ministry 필터 수혜 규정) 도달",
        "tool": "search_provision",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "tech_fee_integrated"},
            {"kind": "returned_not_below", "value": 5},
        ],
    },
    {
        "name": "skip·latency 모니터 — 정상 cold tail 변동 허용(WARN only). 로그 추가가 지연을 키우지 않았는지",
        "tool": "search_provision",
        "args": {"query": "간접비"},
        "asserts": [
            {"kind": "absent_error_code", "value": "timeout"},   # WARN — 비결정 skip 허용
            {"kind": "latency_under", "value": 16.0},            # WARN — cold tail 변동 허용(로그 오버헤드 무시 가능 확인)
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
        ],
    },
]

# Level B(배포 후 NAS 로그 점검) — 사람이 라이브 커넥터로 질의 후 컨테이너 로그를 확인(게이트 판정 아님).
# ★v0.2.10 핵심 검증: 도구 응답이 아니라 *서버 로그*에 fan-out 지연 지표가 남는가 + B2 착수 신호 판독.
# 점검 명령(예): docker logs <컨테이너> | grep 'event=search_fanout_summary'
#               docker logs <컨테이너> | grep 'event=suggest_search_summary'
# B2(v0.2.11 전용 executor) 착수 신호: 요약에 skipped>0 또는 wall_ms>=15000 또는 suggest search_calls 과다.
# 기본 LOG_LEVEL=INFO에서 per-rule(event=fanout_rule)은 출력되지 않아야 함(폭주 방지) — DEBUG에서만 노출.
LEVEL_B_PROMPTS = [
    {
        "category": "observability",
        "probe_prompt": "연구개발비 폭넓게 알려줘",
        "expect_behavior": "라이브 커넥터로 광역 검색이 일어난 뒤, NAS 로그에 'event=search_fanout_summary' 1줄이 "
                           "남고 live_rules/done/skipped/wall_ms/max_rule_ms/slow_rule_count/errors_count가 기록됨. "
                           "skipped=0 & wall_ms<12000이면 풀 여유, skipped>0 또는 wall_ms>=15000이면 v0.2.11 B2 착수 신호.",
    },
    {
        "category": "observability",
        "probe_prompt": "과제 협약 변경 절차 검토해줘",
        "expect_behavior": "suggest_review_sources 경로가 타면 NAS 로그에 'event=suggest_search_summary'가 남고 "
                           "search_calls(1회가 유발한 내부 search 호출 수)·wall_ms·candidates_count가 기록됨. "
                           "search_calls가 과다(예: 두 자리)면 suggest 부하 증폭으로 B2 우선순위 상향.",
    },
    {
        "category": "observability",
        "probe_prompt": "(점검) 기본 LOG_LEVEL=INFO 운영에서 컨테이너 로그 확인",
        "expect_behavior": "'event=fanout_rule'(per-rule DEBUG)이 prod INFO 로그에 보이지 않아야 함(폭주 방지). "
                           "보이면 LOG_LEVEL이 DEBUG로 잘못 설정된 것 — INFO로 정정. 신규 로그에 OC 키·요청 URL 미포함도 함께 확인.",
    },
]
