"""v0.18.0 배포 전 LIVE acceptance spec — 「형태 B redline — 신구조문대비표(oldAndNew) opt-in 노출」.

읽는 법(비프로그래머용): 이번 v0.18.0은 get_provision_detail에 선택 파라미터 include_old_and_new(기본 꺼짐)를
추가하고, 켰을 때만 국가법령정보 OpenAPI의 신구조문대비표(개정 전/후 조문 원문 2열)를 law 문서레벨 응답에
old_and_new 블록으로 부착합니다. 자동(Level A) 검증은 ① 새 opt-in 경로가 LIVE에서 실제 대비표를 받아오는지
② 대비표가 없는 문서(제정 시행령)에서 정직하게 not_provided로 답하는지 ③ 기본(꺼짐) 경로·검색이 회귀하지
않았는지를 확인합니다. 호스트 LLM이 2열 대조를 올바로 소비하는지(마커 해석·'직전 연혁 대비' 비과장·부재 시
무개정 단정 안 함)는 Level B라 배포 후 라이브 커넥터에서 사람이 아래 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★opt-in 신기능 검증(핵심 A·B)은 전부 WARN 클래스(field_equals·absent_error_code)로만 구성 — LIVE 대비표
  제공 여부는 법제처 데이터 사정에 따라 변할 수 있어 hard-BLOCK 부적합(false-block-safe·Andy 최우선 끊김없음).
  BLOCK 후보(fetched_ok·returned_not_below)는 기존 무회귀 검색 체크에만 둔다.
"""

CHECKS = [
    {
        "name": "핵심 A — opt-in 신구조문대비표 부착(중기법 law:281987 → old_and_new.available=True)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987", "include_old_and_new": True},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 문서 도달
            {"kind": "field_equals", "path": "old_and_new.available", "value": True},      # WARN — LIVE 대비표 수신(2026-07-14 실측 실재)
        ],
    },
    {
        "name": "핵심 B — 대비표 부재 정직(제정 기업부설령 law:282915 → not_provided·부재≠무개정 note)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:282915", "include_old_and_new": True},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "old_and_new.available", "value": False},     # WARN — 제정=대비표 부재(실측)
            {"kind": "field_equals", "path": "old_and_new.reason", "value": "not_provided"},  # WARN — 실패(fetch_failed)와 구분
        ],
    },
    {
        "name": "무회귀 A — 기본(opt-in 미지정) 문서레벨 경로 무변(혁신법 law:283849 amendment_kind='일부개정' 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "amendment_kind", "value": "일부개정"},        # WARN — v0.17.0 부착 경로 무회귀
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(opt-in 추가가 검색 fan-out 무접촉)",
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

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.18.0 = 호스트의 old_and_new 소비 품질 + backlog #7(eval 견고성) 흡수.
LEVEL_B_PROMPTS = [
    {
        "category": "★핵심 — 2열 대조(old_and_new) 발견·소비",
        "probe_prompt": "중소기업 기술혁신 촉진법 제10조가 이번 개정으로 개정 전/후 원문이 어떻게 다른지 대조해서 보여줘",
        "expect_behavior": "호스트가 law 문서레벨 get_provision_detail에 include_old_and_new=true를 지정해 old_and_new.rows로 "
                           "개정 전/후 원문을 2열 대조. <P> 마커=변경 구간·'(생 략)'/'(현행과 같음)'=무변경 축약을 올바로 해석하고, "
                           "★'직전 공포 연혁 대비'를 '현행 대비'로 과장하지 않으며 old/new의 공포·시행일자를 함께 제시.",
    },
    {
        "category": "★부재 정직 — 일부개정인데 대비표 없음",
        "probe_prompt": "국가연구개발혁신법 시행규칙은 최근 일부개정됐는데 신구조문대비표로 뭐가 바뀌었는지 보여줘",
        "expect_behavior": "innovation_rule(286879)은 일부개정인데도 대비표 부재(2026-07-14 LIVE 실측). 호스트가 "
                           "available=false·reason=not_provided를 보고 '개정되지 않았다'로 단정하지 않고(부재≠무개정 note 소비), "
                           "amendment_text 또는 document_source_url 공식 원문으로 우회 안내.",
    },
    {
        "category": "eval 견고성(backlog #7) — 비강조 캐주얼 질의 robustness",
        "probe_prompt": "중소기업 기술혁신 촉진법 최근 개정 내용 알려줘",
        "expect_behavior": "'빠짐없이' 완전성 강조가 없는 캐주얼 질의에서도 v0.17.1 소비 가이드(개정 지시 항목을 가지조문 포함 "
                           "점검·생략 시 범위 명시)가 작동하는지 관찰(v0.17.1 eval 범위 한계 보완 — 관측 목적·결함 판정 아님).",
    },
    {
        "category": "무회귀(개정과 무관한 grounding)",
        "probe_prompt": "국가연구개발혁신법상 협약 변경 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "혁신법 family(법§11②중요사항→시행령§14①협의/§14②경미사항→통보)를 MCP grounding으로 인용. "
                           "opt-in 파라미터 추가가 기존 조문 검토를 회귀시키지 않음.",
    },
]
