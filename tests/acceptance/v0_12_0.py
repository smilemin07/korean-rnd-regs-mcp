"""v0.12.0 배포 전 LIVE acceptance spec — 「규정 확대 — 산업기술혁신사업 운영 지침 2건(49→51)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).            [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.12.0의 특수성 — 순수 data 확대(rule_sets.yaml 2건 + 프롬프트 카운트 동기화 + 테스트). 서버 알고리즘·응답 schema·검색/랭킹/fallback·코드 로직 불변(v0.3.0~v0.11.0 동일 패턴). 공유파서 불침투.
  - 신규 2건은 둘 다 admrul 평면 schema = 기존 「산업기술혁신사업 공통 운영요령」과 동형(신규 코드 불요).
  - LIVE acceptance의 본질 = 신규 2건 도달(fan-out reaches + doc-level resolve) + 기존 무회귀 + 신규 별표 size-tier(보안관리요령 BP0000 11,204자 tier-1 verbatim / 평가관리지침 BP0001 46,830자 oversized_pointer=정직 처리).
  - ★N=51 cold fan-out wall(예산 20s)은 이 로컬 하니스가 아니라 **배포 시 NAS 신이미지 cold 스모크**(약-CPU J4125·32 동시연결 rate_limited=0)가 검증한다. latency_under는 WARN advisory.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "신규 도달 + recall — '산업기술' 검색이 신규 운영 지침 2건에 오류 없이 도달 + 결과 반환",
        "tool": "search_provision",
        "args": {"query": "산업기술"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "industry_tech_security"},     # 신규 도달(block 후보)
            {"kind": "fetched_ok", "rule_set_id": "industry_tech_evaluation"},   # 신규 도달(block 후보)
            {"kind": "returned_not_below", "value": 2},                          # recall(block 후보)
            {"kind": "absent_error_code", "value": "timeout"},                   # WARN — fan-out skip 0 기대
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(데이터 확대가 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},               # 실측 ~14
            {"kind": "absent_error_code", "value": "timeout"},         # WARN
            {"kind": "latency_under", "value": 16.0},                  # WARN — cold tail 변동 허용
        ],
    },
    {
        "name": "신규 reg 상세 도달 — 보안관리요령(admrul:2100000122711) 문서레벨 조회 무오류(resolve 정상)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000122711"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},       # WARN — resolve·도달 정상
            {"kind": "absent_error_code", "value": "parse_failed"},    # WARN — 상위 API 장애 신호
        ],
    },
    {
        "name": "신규 reg 상세 도달 — 평가관리지침(admrul:2100000252016·47조문) 문서레벨 조회 무오류(resolve 정상)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000252016"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},       # WARN — resolve 정상
            {"kind": "absent_error_code", "value": "parse_failed"},    # WARN
        ],
    },
    {
        "name": "신규 별표 tier-1 — 보안관리요령 BP0000(11,204자)이 plain_text_verbatim 전문 노출(oversized 아님)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000122711:BP0000"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # ★핵심 별표 전문(WARN)
            {"kind": "absent_error_code", "value": "annex_unavailable_parse_failed"},            # WARN — 별표 파싱 0
            {"kind": "absent_error_code", "value": "invalid_provision_id"},                      # WARN — BP0000 유효
        ],
    },
    {
        "name": "신규 별표 정직 처리 — 평가관리지침 BP0001 추진절차(46,830자)가 oversized_pointer(본문 미수록·over-claim 아님)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000252016:BP0001"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},    # ★대용량 별표=정직 pointer(WARN)
            {"kind": "absent_error_code", "value": "invalid_provision_id"},                      # WARN — BP0001 유효
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.12.0은 순수 data 확대 — 신규 reg가 grounded 인용되는지 + 무회귀.
LEVEL_B_PROMPTS = [
    {
        "category": "신규 reg grounding (연구보안 트랙)",
        "probe_prompt": "산업기술혁신사업의 보안등급 분류 기준과 보안과제 관리 절차를 규정 조문과 함께 알려줘",
        "expect_behavior": "MCP 도구를 호출해 「산업기술혁신사업 보안관리요령」(industry_tech_security)을 검색·인용. 외부 웹 우회 없이 "
                           "get_provision_detail content로 확인(provision_id 제시). v0.11.0 Test1처럼 타깃 질의가 grounded 되는지 = 신규 reg end-to-end.",
    },
    {
        "category": "신규 reg grounding + 정직성 (성과평가 트랙 — oversized 별표)",
        "probe_prompt": "산업기술혁신사업 기술개발 평가의 평가위원회 구성과 평가 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "「산업기술혁신사업 기술개발 평가관리지침」(industry_tech_evaluation) 본문 조문(평가위원회·평가단 등)을 MCP grounding으로 인용. "
                           "추진절차 상세표(별표1)는 대용량이라 도구가 oversized_pointer로 안내 — 이를 '본문 지원'으로 날조하지 않고 공식 원문 링크로 정직 처리하는지 확인.",
    },
    {
        "category": "무회귀(비-신규 조문)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "신규 지침 추가가 기존 핵심 규정 검토를 회귀시키지 않음.",
    },
]
