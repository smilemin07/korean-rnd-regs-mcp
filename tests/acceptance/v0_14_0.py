"""v0.14.0 배포 전 LIVE acceptance spec — 「가지조문(제N조의M) 조회·발견 지원」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경(가지조문 지원)이 LIVE에서 살아있고 기존 동작을
회귀시키지 않았는지' 확인할 항목입니다. 각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).            [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.14.0 핵심 — v0.13.1 라이브 eval이 놓친 바로 그 조문(중소기업 기술혁신 촉진법 시행령 287505의
  2026.6.30 개정 신설 가지조문 제7조의2·제8조의2)이 이제 도구로 반환되는지 LIVE 확인.
  - 상세: get_provision_detail("law:287505:JO000702") → not_found 아님·unit_id 에코(가지조문 도달).
  - 검색: '융자 보증' → sme_tech_decree 도달 + 결과 반환(가지조문이 검색 발견 경로에 유입).
  - 무회귀: 광역 '연구개발비' → 대형 규정 도달 + returned 비회귀(가지조문 유입이 기존 검색을 안 깸).
  ★JO000702 상세는 절대 도달 신호가 WARN(field_equals·absent_error_code)뿐이라 자동 BLOCK 후보가 아님 —
    가지조문 반환의 결정론 확증은 사람 확인(unit_id 에코 + not_found 부재)으로, 회귀 BLOCK은 검색 도달/recall만.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "가지조문 상세 도달 — 시행령 제7조의2(law:287505:JO000702) 조회 무오류·unit_id 에코",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:287505:JO000702"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},        # WARN — 가지조문 도달(미반환 아님)
            {"kind": "absent_error_code", "value": "parse_failed"},     # WARN — 상위 API 장애 신호
            {"kind": "field_equals", "path": "unit_id", "value": "JO000702"},  # WARN — 정확 가지조문 상세
        ],
    },
    {
        "name": "가지조문 검색 발견 — '융자 보증'이 sme_tech_decree(가지조문 보유)에 도달 + 결과 반환",
        "tool": "search_provision",
        "args": {"query": "융자 보증"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "sme_tech_decree"},   # block 후보 — 규정 도달
            {"kind": "returned_not_below", "value": 1},                 # block 후보 — recall
            {"kind": "absent_error_code", "value": "timeout"},          # WARN — fan-out skip 0 기대
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(가지조문 유입이 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                # 실측 ~14
            {"kind": "absent_error_code", "value": "timeout"},          # WARN
            {"kind": "latency_under", "value": 16.0},                   # WARN — cold tail 변동 허용
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.14.0 = v0.13.1 eval이 놓친 그 질의 재현으로 before/after 종결.
LEVEL_B_PROMPTS = [
    {
        "category": "최근 개정 가지조문 grounding (v0.13.1 eval 재현)",
        "probe_prompt": "중소기업 기술혁신 촉진법 시행령의 최근 개정으로 신설된 융자·보증 지원 관련 조문을 규정 근거와 함께 알려줘",
        "expect_behavior": "MCP 도구를 호출해 시행령(sme_tech_decree)의 제7조의2(융자·보증 지원기관)·제8조의2(대상·조건·절차)를 "
                           "get_provision_detail(law:287505:JO000702 등)로 조회·인용. v0.13.1에서 '가지조문 미지원'으로 못 주던 "
                           "신설 조문을 이제 반환함(before/after 종결). ★Level-B: '도구가 반환하게 됨'이 필요조건이며 호스트 surface는 미보장.",
    },
    {
        "category": "무회귀(비-가지조문 grounding)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "가지조문 지원이 기존 본조문 검토를 회귀시키지 않음.",
    },
]
