"""v0.17.1 배포 전 LIVE acceptance spec — 「redline 소비 품질 프롬프트 보강」.

읽는 법(비프로그래머용): 이번 v0.17.1은 코드 로직·응답 데이터 무변경이고, v0.17.0에서 노출한 amendment_text를
호스트 LLM이 더 정확히 소비하도록 프롬프트 문구 3곳만 보강한 patch입니다. 따라서 자동(Level A) 검증에서 확인할 것은
'프롬프트 변경이 기존 응답 데이터/검색을 회귀시키지 않았는지'(무회귀)뿐입니다. 실제 개선(호스트가 개정 조문을
빠짐없이 열거하는지·미검증 연혁을 자제하는지·근거 법률 인용을 보존하는지)은 호스트 LLM 행동(Level B)이라 자동
측정이 불가하며, 배포 후 라이브 커넥터에서 사람이 아래 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★v0.17.1 = 프롬프트 문자열만 변경(응답 데이터 무변) → CHECKS는 v0.17.0의 amendment 부착 경로 + 무회귀가
  그대로 살아있는지만 확인(프롬프트 변경이 응답을 안 깼음을 결정론적으로 입증). 개선 자체는 Level B.
"""

CHECKS = [
    {
        "name": "무회귀 A — 문서레벨 amendment 부착 유지(혁신법 law:283849 amendment_kind='일부개정')",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 문서 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — v0.17.0 부착 경로 무회귀
        ],
    },
    {
        "name": "무회귀 B — 제정 규정 skip 유지(기업부설연구소 시행령 law:282915 amendment_kind='제정')",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:282915"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "amendment_kind", "value": "제정"},           # WARN
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(프롬프트 변경이 검색 무손상)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                  # 실측 ~16-17·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.17.1 = v0.17.0 eval host-side minor 3건이 개선됐는지 관찰.
LEVEL_B_PROMPTS = [
    {
        "category": "★핵심(minor 1 — redline 전수 열거) — 가지조문 포함 개정항목 누락 없이",
        "probe_prompt": "중소기업 기술혁신 촉진법(법률)이 2026년 개정으로 어떤 조문이 어떻게 바뀌었는지 빠짐없이 정리해줘",
        "expect_behavior": "호스트가 문서레벨 get_provision_detail(law)의 amendment_text로 개정 전/후를 정리하되, "
                           "개정문에 담긴 개정 지시 항목을 가지조문(제27조의2 등 제N조의M) 포함 빠짐없이 다룸. "
                           "★v0.17.0 eval에서 개정항목 6개 중 제27조의2제2항을 통째 누락(선택적 초점)했던 것이 개선됐는지 확인. "
                           "분량상 줄일 때는 다룬 범위·생략 항목을 명시하고, amendment_text에 없는 항목을 지어내지 않음(환각 0).",
    },
    {
        "category": "★minor 2 — 제정·타법개정 배경 연혁 자제",
        "probe_prompt": "기업부설연구소등의 연구개발 지원에 관한 법률 시행령은 최근 어떻게 개정됐고, 그 전신 법령은 무엇이야?",
        "expect_behavior": "amendment_kind='제정'을 근거로 '제정(전체 신설)'임을 정확히 인지. "
                           "★전신 법령명·연혁은 도구 응답으로 확인되지 않으므로 단정하지 않고, 일반지식 추정이면 그렇게 표시하거나 생략함. "
                           "v0.17.0 eval에서 '구 연구개발촉진법 시행령'을 미검증 단정한 것이 개선됐는지 확인.",
    },
    {
        "category": "★minor 3 — 개정후 대체문의 근거 법률 citation 보존",
        "probe_prompt": "중소기업 기술혁신 촉진법 제10조 개정으로 융자·보증 관련 문구가 어떻게 바뀌었는지 원문 그대로 알려줘",
        "expect_behavior": "개정후 대체문을 인용할 때 그 안의 근거 법률 인용(예: 중소기업진흥에 관한 법률 제68조 등 법명·조문 번호)을 "
                           "기관명만으로 축약하지 않고 보존함. ★v0.17.0 eval에서 citation을 요약으로 탈락시킨 것이 개선됐는지 확인.",
    },
    {
        "category": "무회귀(개정 내용과 무관한 grounding)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "프롬프트 문구 보강이 기존 조문 검토를 회귀시키지 않음.",
    },
]
