"""v0.2.11 배포 전 LIVE acceptance spec — 「HTTP 멀티테넌트 키 보호 + MCP Registry 마커」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정:
  - fetched_ok      : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                              [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                                     [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                                        [WARN — 차단 안 함]
  - latency_under   : 응답이 value초 미만.                                                          [WARN — 차단 안 함]
  - field_equals    : 응답의 특정 경로 값이 value와 같음.                                            [WARN — 차단 안 함]

★v0.2.11의 특수성 — 자동(A)은 '무회귀', 핵심 가치(키 보호)는 수동(B, 부팅 스모크)으로 확인:
  - v0.2.11의 실질 변경은 HTTP transport 한정 가드(no-oc 차단)와 uvicorn access_log 차단이다.
    이 acceptance 러너는 도구를 직접(코루틴) 호출하므로 HTTP 미들웨어 컨텍스트가 없다 →
    `_is_http_request`가 기본 False → 가드는 inert → '평소(stdio·로컬) 경로'가 그대로 동작한다.
    따라서 아래 Level A CHECKS는 '가드 추가가 평소 검색/조회를 안 깼는지'(무회귀)만 LIVE로 확인한다.
  - 키 보호의 진짜 동작(HTTP no-oc → auth_failed, with-oc → 정상, access log에 ?oc= 미기록, stdio inert)은
    tests/test_tools.py가 결정론으로 단위검증하고, 배포 시 신 이미지 부팅 스모크(LEVEL_B)로 라이브 실증한다.

새 버전 만들 때: 이 파일을 복사해 v0_2_12.py 등으로 두고 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

# 대형/대표 규정(가드 추가가 도달·recall을 회귀시키지 말아야 할 것) — id는 rule_sets.yaml 기준
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "검색 무회귀 — 광역 '연구개발비' 도달·recall·매몰 규정 최상위(가드 inert 경로 정상)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 5}]                       # recall net (block 후보)
            + [{"kind": "field_equals", "path": "results.0.rule_set_id", "value": "rnd_funding_standard"}]  # WARN advisory
        ),
    },
    {
        "name": "핀포인트 무회귀 — '기술료'(ministry 필터 수혜) 도달",
        "tool": "search_provision",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "tech_fee_integrated"},
            {"kind": "returned_not_below", "value": 5},
        ],
    },
    {
        "name": "skip·latency 모니터 — 정상 cold tail 허용(WARN only). 가드/access_log 변경이 평소 경로를 안 깼는지",
        "tool": "search_provision",
        "args": {"query": "간접비"},
        "asserts": [
            {"kind": "absent_error_code", "value": "timeout"},   # WARN — 비결정 skip 허용
            {"kind": "latency_under", "value": 16.0},            # WARN — cold tail 변동 허용
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
        ],
    },
]

# Level B(배포 시 신 이미지 부팅 스모크 + 사람 확인) — HTTP 키 보호의 라이브 실증. 게이트 판정은 사람.
# 신 이미지 부팅: docker run -d --network host -e PORT=18080 ...  (라이브 미스왑 상태에서 검증)
LEVEL_B_PROMPTS = [
    {
        "category": "http-key-protection",
        "probe_prompt": "(부팅 스모크) HTTP no-oc 호출: POST localhost:18080/mcp (initialize) — ?oc= 없이 도구 호출",
        "expect_behavior": "도구 응답이 errors[0].code == 'auth_failed'(원격 호출에는 ?oc= 필요 안내). "
                           "서버 env 키로 silent 조회되지 않음(과금/감사 누출 차단).",
    },
    {
        "category": "http-key-protection",
        "probe_prompt": "(부팅 스모크) HTTP with-oc 호출: localhost:18080/mcp?oc=<유효키> — 정상 검색",
        "expect_behavior": "auth_failed 없이 정상 결과(per-key 클라이언트 경로). 키 보호가 정상 사용자를 막지 않음.",
    },
    {
        "category": "http-key-protection",
        "probe_prompt": "(부팅 스모크) access log 점검: 컨테이너 로그에서 ?oc= 기록 수 = 0",
        "expect_behavior": "uvicorn access_log=False로 요청 라인에 ?oc= 키가 기록되지 않음. "
                           "점검은 패턴 count만(grep -c 'oc='), 요청 라인 출력 금지(키 보호).",
    },
    {
        "category": "regression",
        "probe_prompt": "(부팅 스모크) stdio inert: stdio 기동(env 키)으로 정상 조회 — 가드 무영향",
        "expect_behavior": "stdio(Claude Desktop·uvx)는 env 키가 정상 경로 → 가드 미발화·검색 정상. "
                           "오구현 시 전 stdio 사용자 장애이므로 반드시 라이브 확인.",
    },
]
