"""v0.2.8 배포 전 LIVE acceptance spec — 「검색 결과 관련도 정렬」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 개선이 살아있는지' LIVE로 확인할 항목 목록입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts)은 코드가 아니라 데이터이며, 종류는 5가지로 고정:
  - fetched_ok      : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                              [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                                     [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드(예: timeout)가 0건.                                            [WARN — 차단 안 함]
  - latency_under   : 응답이 value초 미만.                                                          [WARN — 차단 안 함]
  - field_equals    : 응답의 특정 경로 값이 value와 같음.                                            [WARN — 차단 안 함]

v0.2.8 개선의 핵심 = 광역 질의에서 16k 예산 절단 시, 문서 제목이 질문과 직접 일치하는 후순위 규정이
앞순위 규정에 자리를 빼앗겨 매몰되던 결함을 '절단 전 관련도 정렬'로 해소.
  - 결정적 증명(절단 생존·정렬 우선순위)은 mock 단위 테스트가 담당(완전 결정론).
  - 여기 LIVE acceptance는 (1) 내 변경이 기존 도달/recall을 회귀시키지 않았는지(block-eligible net)
    + (2) '연구개발비' 광역 질의의 최상위 결과가 제목 일치 규정(rnd_funding_standard)인지(WARN advisory) 확인.
  - field_equals(results.0.rule_set_id)는 WARN — LIVE 데이터·cold skip 변동에 따라 top이 가변할 수
    있어 차단 신호로 쓰지 않음(false-block 회피). 관련도 회귀의 결정적 게이트는 단위 테스트.

새 버전 만들 때: 이 파일을 복사해 v0_2_9.py 등으로 두고 CHECKS만 그 버전 개선에 맞게 바꾸면 됩니다.
"""

# 대형 규정(관련도 정렬·절단이 도달을 회귀시키지 말아야 할 것) — id는 rule_sets.yaml 기준
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "관련도 정렬 — 매몰 규정 생존·최상위(광역 질의 '연구개발비')",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 5}]                       # recall net (block 후보)
            # ★관련도 advisory(WARN): 문서 제목이 '연구개발비'를 직접 가진 유일 규정이 최상위로 올라오는지.
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
        "name": "skip·latency 모니터 — 정상 cold tail 변동 허용(WARN only)",
        "tool": "search_provision",
        "args": {"query": "간접비"},
        "asserts": [
            {"kind": "absent_error_code", "value": "timeout"},   # WARN — 비결정 skip 허용
            {"kind": "latency_under", "value": 16.0},            # WARN — cold tail 변동 허용
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
        ],
    },
]

# Level B(호스트 LLM 행동) — 배포 후 라이브 커넥터에서 사람이 수동 확인(게이트 판정 아님).
# v0.2.8은 순수 도구 출력(결과 순서) 개선이라 Level A로 대부분 검증되나, '호스트가 상위 결과를
# 실제 인용하는지'는 사람 eval로 확인.
LEVEL_B_PROMPTS = [
    {
        "probe_prompt": "연구개발비 사용에 대해 알려줘 (광역 질의)",
        "expect_behavior": "호스트가 「국가연구개발사업 연구개발비 사용 기준」 규정을 결과 상위에서 발견·인용 "
                           "(v0.2.7에서 매몰되던 규정이 더 이상 누락되지 않음). 날조 없이 LIVE 인용.",
    },
]
