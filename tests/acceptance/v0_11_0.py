"""v0.11.0 배포 전 LIVE acceptance spec — 「규정 확대 — 과기정통부 연구산업진흥법 family 3건(46→49)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.11.0의 특수성 — 순수 data 확대(rule_sets.yaml 3건 + 프롬프트 카운트/라우팅 동기화 + 테스트). 서버 알고리즘·응답 schema·검색/랭킹/fallback·코드 로직 불변(v0.3.0~v0.10.0 동일 패턴). v0.10.1 공유파서(_build_article_content) 불침투.
  - 따라서 LIVE acceptance의 본질 = 신규 3건 도달(fetched_ok·doc-level 조회) + recall + 기존 무회귀 + 신규 시행령 별표(≤5,167자 tier-1)가 plain_text_verbatim으로 전문 노출되는지(oversized 0).
  - 전건 중첩 schema라 v0.10.1 호 아래 목 파싱 혜택 자동. 시행규칙은 별표0·서식15(BP 미노출)→article.
  - ★N=49 cold fan-out wall(예산 20s)은 이 로컬 하니스가 아니라 **배포 시 NAS 신이미지 cold 스모크**(약-CPU J4125·32 동시연결 rate_limited=0)가 검증한다. latency_under는 WARN advisory.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "신규 도달 + recall — '연구산업' 검색이 연구산업진흥법 family(법·령) 도달",
        "tool": "search_provision",
        "args": {"query": "연구산업"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "research_industry_act"},     # 신규 도달(block 후보)
            {"kind": "fetched_ok", "rule_set_id": "research_industry_decree"},
            {"kind": "returned_not_below", "value": 2},                         # recall(block 후보)
            {"kind": "absent_error_code", "value": "timeout"},                  # WARN — fan-out skip 0 기대
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
        "name": "신규 reg 상세 도달 — 법률(law:231603) 문서레벨 조회 무오류",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:231603"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},       # WARN — resolve·도달 정상
            {"kind": "absent_error_code", "value": "parse_failed"},    # WARN — 상위 API 장애 신호
        ],
    },
    {
        "name": "신규 reg 상세 도달 — 시행규칙(law:262117·4조문·search 비의존) 문서레벨 조회 무오류",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:262117"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},       # WARN — 소형 시행규칙 resolve 정상
            {"kind": "absent_error_code", "value": "parse_failed"},    # WARN
        ],
    },
    {
        "name": "신규 시행령 별표 tier-1 — law:261923:BP0001(≤5,167자)이 plain_text_verbatim 전문 노출(oversized 아님)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:261923:BP0001"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # ★소형 별표 전문(WARN)
            {"kind": "absent_error_code", "value": "annex_unavailable_parse_failed"},            # WARN — 별표 파싱 0
            {"kind": "absent_error_code", "value": "invalid_provision_id"},                      # WARN — BP0001 유효
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.11.0은 순수 data 확대 — 신규 reg가 grounded 인용되는지 + 무회귀.
LEVEL_B_PROMPTS = [
    {
        "category": "신규 reg grounding",
        "probe_prompt": "연구산업진흥법상 연구개발서비스업 또는 연구산업 지원의 정의·근거를 규정 조문과 함께 알려줘",
        "expect_behavior": "MCP 도구를 호출해 「연구산업진흥법」 family(research_industry_*)를 검색·인용. 외부 웹 우회 없이 "
                           "get_provision_detail content로 확인(provision_id 제시). v0.8.0 Test2·v0.10.0 Test1처럼 타깃 질의가 grounded 되는지 = 신규 reg end-to-end.",
    },
    {
        "category": "무회귀(비-신규 조문)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "신규 family 추가가 기존 핵심 규정 검토를 회귀시키지 않음(v0.10.1 Test2 동형).",
    },
]
