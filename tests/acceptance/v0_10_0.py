"""v0.10.0 배포 전 LIVE acceptance spec — 「규정 확대 — 과기정통부 기업부설연구소 family 3건(43→46)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.10.0의 특수성 — 순수 data 확대(rule_sets.yaml 3건 + 프롬프트 카운트 동기화 + 테스트). 서버 알고리즘·응답 schema·검색/랭킹/fallback·코드 로직 불변(v0.3.0~v0.9.0 동일 패턴).
  - 따라서 LIVE acceptance의 본질 = 신규 3건 도달(fetched_ok) + recall + 기존 무회귀 + 신규 oversized 별표(시행규칙 BP0000·20,358자)가 기존 v0.6.0 size-tier 가드로 oversized_pointer 처리되는지.
  - ★대형 별표 실하드웨어 size 처리·N=46 cold fan-out wall(예산 20s)은 이 로컬 하니스가 아니라 **배포 시 NAS 신이미지 cold 스모크**(약-CPU J4125·32 동시연결 rate_limited=0)가 검증한다. latency_under는 WARN advisory.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "신규 3건 도달 + recall — '기업부설연구소' 검색이 corp_lab family 전건 도달",
        "tool": "search_provision",
        "args": {"query": "기업부설연구소"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "corp_lab_act"},     # 신규 도달(block 후보)
            {"kind": "fetched_ok", "rule_set_id": "corp_lab_decree"},
            {"kind": "fetched_ok", "rule_set_id": "corp_lab_rule"},
            {"kind": "returned_not_below", "value": 3},                # recall(block 후보)
            {"kind": "absent_error_code", "value": "timeout"},         # WARN — fan-out skip 0 기대
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(데이터 확대가 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},               # 실측 14
            {"kind": "absent_error_code", "value": "timeout"},         # WARN
            {"kind": "latency_under", "value": 16.0},                  # WARN — cold tail 변동 허용
        ],
    },
    {
        "name": "신규 oversized 별표 — 시행규칙 별표0000(20,358자)이 size-tier 가드로 oversized_pointer 처리",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283223:BP0000"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # ★핵심 — 대형 별표 안전 강등(WARN)
            {"kind": "absent_error_code", "value": "annex_unavailable_parse_failed"},          # WARN — 별표 파싱 실패 0
            {"kind": "absent_error_code", "value": "invalid_provision_id"},                    # WARN — BP0000 유효
        ],
    },
    {
        "name": "신규 reg 상세 도달 — 법률(law:282553) 문서레벨 조회 무오류",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:282553"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},       # WARN — resolve·도달 정상
            {"kind": "absent_error_code", "value": "parse_failed"},    # WARN — 상위 API 장애 신호
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.10.0은 순수 data 확대 — 신규 reg가 grounded 인용되는지 + oversized 별표 정직 처리.
LEVEL_B_PROMPTS = [
    {
        "category": "신규 reg grounding",
        "probe_prompt": "기업부설연구소 인정 요건을 규정 근거(조문)와 함께 알려줘",
        "expect_behavior": "MCP 도구를 호출해 「기업부설연구소등의 연구개발 지원에 관한 법률」 family(corp_lab_*)를 검색·인용. 외부 웹 우회 없이 "
                           "get_provision_detail content로 확인(provision_id 제시). v0.8.0 Test2·v0.9.0 연구윤리처럼 타깃 질의가 grounded 되는지 = 신규 reg end-to-end.",
    },
    {
        "category": "oversized 별표 정직 처리",
        "probe_prompt": "기업부설연구소등의 연구개발 지원에 관한 법률 시행규칙의 별표(서식 관련) 본문을 알려줘",
        "expect_behavior": "시행규칙 별표(20,358자)는 oversized이므로 get_provision_detail이 oversized_pointer(본문 미수록·content_format≠plain_text_verbatim·공식 링크)를 "
                           "반환 → 호스트가 본문을 날조하지 않고 공식 원문 링크를 안내. size-tier 가드 end-to-end(혁신법 시행령 별표2/7 동형).",
    },
]
