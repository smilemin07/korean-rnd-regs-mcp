"""v0.15.0 배포 전 LIVE acceptance spec — 「law 조문 개정 이력(공포일) 발견성」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경(개정 이력 발견성)이 LIVE에서 살아있고 기존 동작을
회귀시키지 않았는지' 확인할 항목입니다. 각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★v0.15.0 핵심 — v0.13.1 라이브 eval shortfall A(호스트가 어느 조문이 개정됐는지 몰라 법률 개정을
  false-negative로 놓침)를 해소하는 doc-level `latest_history` 필드가 LIVE에서 작동하는지 확인.
  - 문서레벨 목록: get_provision_detail("law:281987") → 제10조·제18조 항목에 latest_history(개정/신설 2025.12.30) 부착.
  - JO 상세: get_provision_detail("law:281987:JO0010") → latest_history 동반.
  - 신설 조문: get_provision_detail("law:287505:JO000702") → latest_history "본조신설 …"(참고자료 유일 소스).
  - 무회귀: 광역 '연구개발비' → 대형 규정 도달 + returned 비회귀(개정 이력 유입이 기존 검색을 안 깸).
  ★latest_history 값 확인은 결정론이나 신호가 field_equals/absent_error_code(WARN)라 자동 BLOCK 후보가 아님 —
    개정 발견성의 결정론 확증은 사람 확인(latest_history 부착), 회귀 BLOCK은 대형 규정 도달/recall만.

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "shortfall A 발견 — 중기법(law:281987) 문서레벨 조회 무오류(articles latest_history 부착은 사람 확인)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},        # WARN — 문서 도달
            {"kind": "absent_error_code", "value": "parse_failed"},     # WARN — 상위 API 장애 신호
        ],
    },
    {
        "name": "개정 조문 상세 — 중기법 제10조(law:281987:JO0010) 도달·latest_history 동반(사람 확인)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987:JO0010"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},        # WARN — 조문 도달(2026 개정 조문)
            {"kind": "field_equals", "path": "unit_id", "value": "JO0010"},  # WARN — 정확 조문 상세
        ],
    },
    {
        "name": "신설 가지조문 상세 — 시행령 제7조의2(law:287505:JO000702) 도달(latest_history '본조신설'은 사람 확인)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:287505:JO000702"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},        # WARN — 가지조문 도달
            {"kind": "field_equals", "path": "unit_id", "value": "JO000702"},  # WARN
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(개정 이력 유입이 검색을 안 깸)",
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.15.0 = shortfall A 그 질의 before/after + 호스트 오독 검증.
LEVEL_B_PROMPTS = [
    {
        "category": "최근 개정 조문 발견 (v0.13.1 shortfall A 재현)",
        "probe_prompt": "중소기업 기술혁신 촉진법(법률)의 2026년 최근 개정으로 바뀐 조문이 무엇인지 규정 근거와 함께 알려줘",
        "expect_behavior": "MCP 도구로 문서레벨 get_provision_detail(law:281987)을 호출해 articles 목록의 latest_history로 "
                           "최근 개정 조문(제10조 융자 지원 도입·제18조 SW 사용료 지원 신설 = 개정/신설 2025.12.30)을 식별·조회·인용. "
                           "v0.13.1에서 '법률 개정 확인 안 됨'으로 false-negative였던 것이 발견됨(before/after 종결). "
                           "★Level-B: 서버가 latest_history를 정확히 내려주는 것이 필요조건이며 호스트 surface는 미보장.",
    },
    {
        "category": "★호스트 오독 검증 (신규 false-negative 방지)",
        "probe_prompt": "국가연구개발혁신법 제1조(목적)는 최근에 개정된 적이 있어?",
        "expect_behavior": "제1조에 latest_history가 없으면(=최근 개정 마커 미부착) 호스트가 '개정된 적 없다'고 단정하지 않고 "
                           "'이 도구가 캡처한 최근 개정 마커가 없다'는 정도로 정직하게 답해야 함(부재 ≠ 미개정 보증). "
                           "값의 날짜를 시행일로 오인하지 않는지도 관찰(값=공포일).",
    },
    {
        "category": "무회귀(개정 이력과 무관한 grounding)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "개정 이력 필드 추가가 기존 조문 검토를 회귀시키지 않음.",
    },
]
