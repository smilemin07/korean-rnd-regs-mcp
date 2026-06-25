"""v0.9.1 배포 전 LIVE acceptance spec — 「fan-out 전용 bounded executor — 풀 큐잉 latency 제거 (B2)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.9.1의 특수성 — 내부 동시성만 변경(전용 ThreadPoolExecutor 32 + TTLCache 직렬화 Lock). 응답 schema·검색/랭킹/fallback·규정 수(43) 불변.
  - 따라서 LIVE acceptance의 본질 = 순수 무회귀(executor/lock 교체가 fan-out 도달·recall을 안 깼는지) + 무-skip(전용 풀이 큐잉을 줄여 timeout skip 0).
  - ★핵심 개선(cold fan-out 풀 큐잉 제거 → wall 감소)은 이 로컬 하니스가 아니라 **배포 시 NAS 신이미지 cold 스모크**가 검증한다(약-CPU J4125 실하드웨어 + 32 동시연결 rate_limited=0). 여기 latency_under는 WARN advisory(로컬 환경 변동).
  - 정적/결정론(pytest 296): executor 구성(max_workers 32)·offload 단일 진입점·asyncio.to_thread 실호출 0·_cache_lock 존재·★lock-never-wraps-network 정적 게이트(test_b2_executor.py)가 하드게이트.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(전용 executor 교체가 fan-out을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]  # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 10}]                       # recall net (block 후보; 실측 14)
            + [{"kind": "absent_error_code", "value": "timeout"}]                 # ★B2: 전용 풀 → skip 0 기대(WARN)
            + [{"kind": "latency_under", "value": 16.0}]                          # WARN — cold tail 변동 허용
        ),
    },
    {
        "name": "fan-out 무-skip — '기술료' 도달 + timeout skip 0(전용 풀이 큐잉 완화)",
        "tool": "search_provision",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "returned_not_below", "value": 1},
            {"kind": "absent_error_code", "value": "timeout"},   # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},  # WARN — 상위 API 장애 신호
        ],
    },
    {
        "name": "신규(v0.9.0) regs 무회귀 — '연구윤리'·'산학협력'이 전용 executor 경유로도 도달",
        "tool": "search_provision",
        "args": {"query": "연구윤리"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "research_ethics_guideline"},
            {"kind": "returned_not_below", "value": 1},
        ],
    },
    {
        "name": "cold latency advisory — '협약 변경'(전용 32-worker는 8스레드보다 빨라야·WARN only)",
        "tool": "search_provision",
        "args": {"query": "협약 변경"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "absent_error_code", "value": "timeout"},   # WARN
            {"kind": "latency_under", "value": 14.0},            # WARN — 32-worker 기대치(로컬 ~5s)·NAS는 별도 스모크
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.9.1은 내부 동시성만 — 호스트 LLM 행동 변화 없음.
# 따라서 Level-B 본질 = '정상 사용이 배포 후에도 깨지지 않는가'의 기본 스모크 1건.
# v0.9.1의 진짜 검증(cold fan-out wall 감소·rate_limited=0)은 배포 시 NAS 신이미지 cold 스모크(사람).
LEVEL_B_PROMPTS = [
    {
        "category": "no-regression-smoke",
        "probe_prompt": "국가연구개발사업 연구개발비 사용 기준에서 간접비 항목을 규정 근거와 함께 알려줘",
        "expect_behavior": "MCP 도구를 호출해 「연구개발비 사용 기준」 조문을 근거(provision_id)와 함께 인용(v0.9.0과 동일 — "
                           "전용 executor 전환이 응답 내용을 바꾸지 않음). 외부 우회 없이 get_provision_detail content로 확인. "
                           "(v0.9.1은 내부 동시성만 변경 — 새 호스트 행동 없음. 핵심 latency 개선은 NAS cold 스모크가 검증.)",
    },
]
