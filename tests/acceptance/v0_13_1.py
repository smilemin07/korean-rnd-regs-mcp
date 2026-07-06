"""v0.13.1 배포 전 LIVE acceptance spec — 「manifest 현행 정합성 — 중소기업 기술혁신 촉진법 family 시행일·doc_id 동기화」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).            [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.13.1의 특수성 — 순수 data 정합 패치(rule_sets.yaml 4필드 = 중소기업 기술혁신 촉진법 법률·시행령의 api_doc_id·effective_date를
  2026-07-01 개정 발효분으로 현행화). 서버 알고리즘·응답 schema·검색/랭킹/fallback·코드 로직·규정 수(52) 불변. 신규 코드 0줄.
  - manifest fallback doc_id(281987·287505) 정합은 정적 단위 테스트(test_sme_tech_family_current_docids_v0131)가 잠근다.
    ★LIVE acceptance의 fetched_ok는 search-first가 title로 resolve하므로 manifest 값 자체를 검증하지 못한다(도달만 확인).
    따라서 여기서는 (1) 두 규정이 여전히 오류 없이 도달·recall + (2) 광역 무회귀 만 확인하고, fallback 값 정합은 단위 테스트가 담당.
  - N=52 cold fan-out wall(예산 20s)은 이 로컬 하니스가 아니라 배포 시 NAS 신이미지 cold 스모크가 검증한다. latency_under는 WARN advisory.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "정합 대상 도달 + recall — '중소기업 기술혁신' 검색이 법률·시행령에 오류 없이 도달 + 결과 반환",
        "tool": "search_provision",
        "args": {"query": "중소기업 기술혁신"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "sme_tech_act"},      # 갱신 대상(block 후보)
            {"kind": "fetched_ok", "rule_set_id": "sme_tech_decree"},   # 갱신 대상(block 후보)
            {"kind": "returned_not_below", "value": 1},                 # recall(block 후보)
            {"kind": "absent_error_code", "value": "timeout"},          # WARN — fan-out skip 0 기대
        ],
    },
    {
        "name": "정합 대상 상세 도달 — 시행령(현행 MST) 문서레벨 조회 무오류(resolve 정상)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:287505"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},       # WARN — 신 MST resolve·도달 정상
            {"kind": "absent_error_code", "value": "parse_failed"},    # WARN — 상위 API 장애 신호
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(데이터 정합 패치가 검색을 안 깸)",
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
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.13.1은 순수 data 현행 정합 — 신규 grounding 없음. 갱신 대상 grounding + 무회귀.
LEVEL_B_PROMPTS = [
    {
        "category": "현행 정합 grounding (갱신 대상)",
        "probe_prompt": "중소기업 기술혁신 촉진법과 시행령의 최근 개정 사항을 규정 조문·시행일과 함께 알려줘",
        "expect_behavior": "MCP 도구를 호출해 중소기업 기술혁신 촉진법(sme_tech_act)·시행령(sme_tech_decree)을 검색·인용. "
                           "현행 시행일(2026-07-01)을 도구 응답 기준으로 안내하고, 조문 본문을 grounded 인용(외부 stale 미인용).",
    },
    {
        "category": "무회귀(비-갱신 규정)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "중소기업 family 정합 패치가 기존 핵심 규정 검토를 회귀시키지 않음.",
    },
]
