"""v0.13.0 배포 전 LIVE acceptance spec — 「규정 확대 — 혁신도전형 고시 + 별지 정직 caveat(51→52)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).            [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.13.0의 특수성 — 순수 data 확대(rule_sets.yaml 1건 + 프롬프트 카운트 동기화 + 테스트). 서버 알고리즘·응답 schema·검색/랭킹/fallback·코드 로직 불변(v0.3.0~v0.12.0 동일 패턴·9번째). 공유파서 불침투.
  - 신규 1건은 admrul 평면 schema = 기존 평면 admrul 19건과 동형(신규 코드 불요). 조문 8건 전부 tier-1(최대 1,272자).
  - ★별지 정직 caveat: 핵심 분류 기준(밀착관리형·공개경쟁형)은 별지 1(274자) 수록 — 별표구분='별지'는 BP 미노출(by-design)이라
    도구 응답에 별표 목록이 비고(annexes []), doc-level warnings의 '부속문서 본문 조회 불가' 일반 경고(v0.2.2)가 정직 신호.
    이 형상은 단위 테스트(test_doc_level_forms_only_warning_innovation_challenge_v0130)가 mock으로 잠그고,
    LIVE에서는 문서레벨 조회 무오류(도달)로 확인.
  - LIVE acceptance의 본질 = 신규 1건 도달(fan-out reaches + doc-level resolve) + 핵심 조문(제5조 지정 절차) 본문 전문 + 기존 무회귀.
  - ★N=52 cold fan-out wall(예산 20s)은 이 로컬 하니스가 아니라 **배포 시 NAS 신이미지 cold 스모크**가 검증한다. latency_under는 WARN advisory.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "신규 도달 + recall — '혁신도전형' 검색이 신규 고시에 오류 없이 도달 + 결과 반환",
        "tool": "search_provision",
        "args": {"query": "혁신도전형"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "innovation_challenge_criteria"},  # 신규 도달(block 후보)
            {"kind": "returned_not_below", "value": 1},                              # recall(block 후보)
            {"kind": "absent_error_code", "value": "timeout"},                       # WARN — fan-out skip 0 기대
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
        "name": "신규 reg 상세 도달 — 혁신도전형 고시(admrul:2100000253392) 문서레벨 조회 무오류(resolve 정상)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000253392"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},       # WARN — resolve·도달 정상
            {"kind": "absent_error_code", "value": "parse_failed"},    # WARN — 상위 API 장애 신호
        ],
    },
    {
        "name": "신규 핵심 조문 전문 — 제5조 지정 절차(1,272자=최대 조문)가 plain_text_verbatim 전문 노출",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000253392:JO0005"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # ★실무 가치 본문(WARN)
            {"kind": "absent_error_code", "value": "not_found"},                                  # WARN — JO0005 유효
            {"kind": "absent_error_code", "value": "invalid_provision_id"},                       # WARN
        ],
    },
    {
        "name": "별지 위임 조문 — 제4조(별지 1 위임 문구)가 본문 전문 노출(분류 기준 본문은 별지라 미수록=정직)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000253392:JO0004"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 위임 문구 자체는 전문
            {"kind": "absent_error_code", "value": "not_found"},                                  # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.13.0은 순수 data 확대 + 별지 정직 caveat — 신규 reg grounding + 별지 정직 처리 + 무회귀.
LEVEL_B_PROMPTS = [
    {
        "category": "신규 reg grounding + ★별지 정직성 (핵심 검증)",
        "probe_prompt": "혁신도전형 연구개발사업군의 지정 절차와 유형 분류 기준을 규정 조문과 함께 알려줘",
        "expect_behavior": "MCP 도구를 호출해 「혁신도전형 연구개발사업군의 지정 및 분류 기준 등에 관한 고시」(innovation_challenge_criteria)를 검색·인용. "
                           "지정 절차(제5조)·지정 해제(제6조)는 본문 조문 grounded 인용. ★유형 분류 기준(밀착관리형·공개경쟁형)은 별지 1 수록이라 "
                           "도구가 본문을 못 주므로 — 호스트가 이를 날조하지 않고 '별지 수록·도구 미제공·공식 원문 확인' 취지로 정직 고지하는지 확인(over-claim 여부가 핵심).",
    },
    {
        "category": "무회귀(비-신규 조문)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "신규 고시 추가가 기존 핵심 규정 검토를 회귀시키지 않음.",
    },
]
