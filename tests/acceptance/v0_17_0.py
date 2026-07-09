"""v0.17.0 배포 전 LIVE acceptance spec — 「개정 전/후 대조(redline) 최소형」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경(law 문서레벨 응답에 amendment_text·amendment_kind 노출)이
LIVE에서 살아있고 기존 동작을 회귀시키지 않았는지' 확인할 항목입니다. 각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts)
종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★v0.17.0 핵심 — v0.16.0 라이브 eval 관찰(호스트가 '어느 조문이 개정됐나'는 1턴에 풀게 되자 후속으로 '무엇이
  바뀌었나'(개정 전/후)를 답하려다 도구가 현행 원문+마커만 줘 아쉬워함)을 해소하는, law 문서레벨 응답의
  amendment_text(개정문·개정지시문 산문)·amendment_kind(제개정구분) 노출이 LIVE에서 작동하는지 확인.
  size 규칙(whole-or-omit)의 실데이터 동작(부착 25·제정 skip 3·생략 1)은 배포 전 LIVE size 실측·사람 확인으로도
  교차 확인하되, 여기서는 결정론 가능한 부착/제정/생략 경로의 대표 규정과 무회귀만 자동 판정.

  - 일부개정 규정(혁신법 283849): 문서레벨 amendment_kind='일부개정' 부착(field_equals).
  - 제정 규정(기업부설연구소 시행령 282915): amendment_kind='제정' 부착·amendment_text는 skip(제정 신호).
  - 생략 경로(산업기술 시행령 285891): base 최대라 예산 초과 → amendment_text_omitted=true(whole-or-omit).
  - 무회귀 핵심: 광역 '연구개발비' → 대형 규정 도달 + returned 비회귀(문서레벨 필드 추가가 검색을 안 깸).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

CHECKS = [
    {
        "name": "일부개정 규정 amendment 노출 — 혁신법(law:283849) 문서레벨에 amendment_kind='일부개정'",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 문서 도달
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — amendment 부착 확인
        ],
    },
    {
        "name": "제정 규정 skip — 기업부설연구소 시행령(law:282915) amendment_kind='제정'(amendment_text는 skip)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:282915"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "amendment_kind", "value": "제정"},           # WARN — 제정 신호(text skip은 사람/size 실측 확인)
        ],
    },
    {
        "name": "생략 경로(whole-or-omit) — 산업기술 시행령(law:285891) base 최대라 amendment_text_omitted=true",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285891"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 문서 도달·articles 보존
            {"kind": "field_equals", "path": "amendment_text_omitted", "value": True},    # WARN — 생략 경로 LIVE 확인
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(문서레벨 필드 추가가 검색 무손상)",
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.17.0 = 개정 발견 후 "무엇이 바뀌었나" 후속 질의를
# 문서레벨 amendment_text로 답하는지(개정문 산문을 조문별 완전 diff로 과장하지 않는지·제정 구분·생략 안내).
LEVEL_B_PROMPTS = [
    {
        "category": "★핵심 — '무엇이 바뀌었나'(개정 전/후) 문서레벨 amendment_text로 답",
        "probe_prompt": "중소기업 기술혁신 촉진법(법률)이 2026년 개정으로 제10조·제18조 등에서 구체적으로 어떤 문구가 어떻게 바뀌었는지 알려줘",
        "expect_behavior": "호스트가 문서레벨 get_provision_detail(law)로 amendment_text(개정문)를 받아, "
                           "제10조 제목 '출연'→'지원' 등 실제 개정 전/후 문구를 인용. v0.16.0에서는 현행 원문+마커만 있어 "
                           "'무엇이 바뀌었나'에 diff를 못 줬던 것이 before/after로 개선됨. "
                           "★amendment_text는 최신 개정분의 원 개정지시문 산문이지 조문별 완전 대조표가 아니므로, "
                           "호스트가 '조문별 완전 redline'으로 과장하지 않고 개정문 근거로 정직하게 답하는지 관찰.",
    },
    {
        "category": "★제정 법령 구분 — amendment_kind='제정'이면 전체 신설",
        "probe_prompt": "기업부설연구소등의 연구개발 지원에 관한 법률 시행령은 최근 어떻게 개정됐어?",
        "expect_behavior": "amendment_kind='제정'을 근거로 '전부 개정이 아니라 제정(전체 신설)'임을 인지하고, "
                           "개정문 blob(서명부·부칙)을 조문별 개정으로 오독하지 않음. amendment_text 부재를 정직 처리.",
    },
    {
        "category": "무회귀(개정 내용과 무관한 grounding)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "문서레벨 amendment 필드 추가가 기존 조문 검토를 회귀시키지 않음.",
    },
]
