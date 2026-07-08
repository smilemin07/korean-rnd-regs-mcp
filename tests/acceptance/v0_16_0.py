"""v0.16.0 배포 전 LIVE acceptance spec — 「검색 경로 개정 이력 노출」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경(검색 결과 law 조문에 latest_history 노출)이 LIVE에서
살아있고 기존 동작을 회귀시키지 않았는지' 확인할 항목입니다. 각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts)
종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★v0.16.0 핵심 — v0.15.0 라이브 eval 발견 #1(호스트의 '최근 개정 조문?' 기본 본능이 키워드 검색이라,
  문서레벨 전용이던 latest_history를 1턴에 발견 못 함)을 해소하는 '검색 결과 law 조문의 latest_history 부착'이
  LIVE에서 작동하는지 확인. 단 검색 결과 항목의 latest_history 부착 여부는 매치 순서·부착률(문서편차 0~40%대)에
  좌우되어 field_equals(고정 path)로 결정론 단정이 어려우므로, 부착 자체 확인은 배포 전 size 실측(신코드로 search
  '개정' before/after)·사람 확인으로 하고, 여기서는 회귀 BLOCK(대형 규정 도달·recall)만 자동 판정.

  - 개정 의도 질의: search_provision('개정') → 대형 law 규정 도달 + recall 비회귀(개정 마커 유입이 검색을 안 깸).
  - 무회귀 핵심: 광역 '연구개발비' → 대형 규정 도달 + returned 비회귀(latest_history 유입으로 인한 조기 절단이
    무회귀 하한을 깨지 않음 — 실측 17→16 수준, 하한 10 크게 상회).
  - 개정 조문 상세: get_provision_detail('law:281987:JO0010') 여전히 도달(v0.15.0 doc-level 경로 무회귀).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "개정 의도 질의 — search_provision('개정') 대형 law 규정 도달 + recall(개정 신호 유입이 검색 무손상)",
        "tool": "search_provision",
        "args": {"query": "개정"},
        "asserts": [
            {"kind": "returned_not_below", "value": 10},                # 실측 ~14 (예산-포화 질의)
            {"kind": "absent_error_code", "value": "timeout"},          # WARN
            {"kind": "latency_under", "value": 16.0},                   # WARN — cold tail 변동 허용
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(latest_history 유입 조기 절단이 하한 무손상)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                # 실측 17→16 수준·하한 10 상회
            {"kind": "absent_error_code", "value": "timeout"},          # WARN
            {"kind": "latency_under", "value": 16.0},                   # WARN
        ],
    },
    {
        "name": "개정 조문 상세 무회귀 — 중기법 제10조(law:281987:JO0010) 도달(v0.15.0 doc-level 경로 불변)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987:JO0010"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},        # WARN — 조문 도달
            {"kind": "field_equals", "path": "unit_id", "value": "JO0010"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.16.0 = 발견 #1 그 질의를 검색-first로 재실행,
# 검색 결과에 latest_history가 실려 호스트가 1턴에 개정 조문을 인지하는지 before/after.
LEVEL_B_PROMPTS = [
    {
        "category": "★발견 #1 재현 — 검색-first 경로에서 개정 조문 1턴 발견",
        "probe_prompt": "중소기업 기술혁신 촉진법(법률)의 2026년 최근 개정으로 신설·변경된 조문이 무엇인지 규정 근거와 함께 알려줘",
        "expect_behavior": "호스트가 search_provision/suggest로 먼저 다가가더라도, 검색 결과의 law 조문 매치에 "
                           "latest_history(예 '개정 2025.12.30(공포)')가 실려 있어 제10조 융자·제18조 SW 사용료 등 "
                           "최근 개정 조문을 1턴에 인지·조회·인용. v0.15.0에서는 검색 경로에 신호가 없어 nudge 후 "
                           "2턴에야 문서레벨 순회로 도달했던 것이 before/after로 개선됨. "
                           "★Level-B: 검색 결과에 latest_history가 실리는 것은 결정론(서버)이나 호스트가 그걸 활용하는지는 미보장. "
                           "검색 매치는 키워드 한정이므로 전수 확인은 문서레벨 articles로 안내하는지도 관찰.",
    },
    {
        "category": "★호스트 오독 검증 (부재 ≠ 미개정·날짜=공포일)",
        "probe_prompt": "국가연구개발혁신법에서 최근 개정된 조문을 검색해서 알려줘",
        "expect_behavior": "검색 결과의 latest_history 날짜를 시행일로 오인하지 않고 공포일로 정확히 해석. "
                           "검색에 안 걸린 조문을 '개정 안 됨'으로 단정하지 않고, 전수 확인은 문서레벨 조회로 유도.",
    },
    {
        "category": "무회귀(개정 이력과 무관한 grounding)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "검색 결과 latest_history 필드 추가가 기존 조문 검토를 회귀시키지 않음.",
    },
]
