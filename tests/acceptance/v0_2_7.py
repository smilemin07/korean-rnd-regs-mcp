"""v0.2.7 배포 전 LIVE acceptance spec — 「구동 안정성 강화」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 개선이 살아있는지' LIVE로 확인할 항목 목록입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts)은 코드가 아니라 데이터이며, 종류는 5가지로 고정:
  - fetched_ok      : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달). ★대형 규정이 안 끊기는지 확인.  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상.                                                    [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드(예: timeout)가 0건.                                            [WARN — 차단 안 함]
  - latency_under   : 응답이 value초 미만.                                                          [WARN — 차단 안 함]
  - field_equals    : 응답의 특정 경로 값이 value와 같음.                                            [WARN — 차단 안 함]

v0.2.7 개선의 핵심 위험 = read timeout을 30s→12s로 줄여 '정상이지만 느린 대형 규정'을 끊을 수 있는가.
따라서 ICT 관리규정(139k)·혁신법 시행령(52k)·연구개발비 사용기준(67k) 같은 대형 규정의 *도달*이 핵심 신호.
skip(timeout)·latency는 정상 cold tail(비결정 네트워크 변동)에서도 가끔 발생하므로 WARN(차단 금지).

새 버전 만들 때: 이 파일을 복사해 v0_2_8.py 등으로 두고 CHECKS만 그 버전 개선에 맞게 바꾸면 됩니다.
"""

# 대형 규정(read 12s가 끊지 말아야 할 것) — id는 rule_sets.yaml 기준
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "대형 규정 도달 — read 12s가 대형 규정을 끊지 않음(광역 질의 '연구개발비')",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]
            + [{"kind": "returned_not_below", "value": 5}]
        ),
    },
    {
        "name": "핀포인트 안정 — '기술료'(ministry 필터 수혜 규정 포함) 도달",
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

# Level B(호스트 LLM 행동) 검증: v0.2.7은 순수 도구 출력(안정성) 개선이라 Level B 없음.
# (Level B 있는 버전은 여기에 {"probe_prompt": "...", "expect_behavior": "..."} 목록을 두면
#  러너가 '배포 후 라이브 커넥터에서 사람이 수동 확인'할 프롬프트로 출력만 함 — 게이트 판정 아님.)
LEVEL_B_PROMPTS = []
