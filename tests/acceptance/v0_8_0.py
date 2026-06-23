"""v0.8.0 배포 전 LIVE acceptance spec — 「R&D 규정 지원 확대 — 교육부 학술진흥법 family 3건 (36→39)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.8.0의 특수성 — 순수 data(코드 무변경) 확대. 신규 규정 도달성은 자동(A·회귀/도달)으로, '검색 매칭·인용·미지원 정직성'의 호스트 행동은 배포 후 수동(B):
  - 3건 신규 학술진흥법(법·시행령·시행규칙)이 fan-out에서 오류 없이 조회되고(fetched_ok), '학술진흥' 질의가 결과를 반환하는지(returned_not_below) LIVE 확인.
  - 3건 모두 law target·중첩 schema(평면 admrul 아님) → 기존 law family와 동일 배선·무코드 동작. manifest 적재·api_target·ministry·hierarchy는 pytest(test_hakjin_family_registered_v080)가 결정론으로 하드게이트.
  - ★LIVE 게이트(2026-06-23) 확정: 정확 title('학술진흥법'/'학술진흥법 시행령'/'학술진흥법 시행규칙') + ministry=교육부 정확일치 resolve가 유일 현행 문서 1건을 집음(트랙 충돌·동명이종·약칭 0). 메모상 '트랙 판별 가드'는 이 3건 family에 불요 — 순수 yaml 데이터로 안전. 아래 LIVE 항목은 도달성만 확인한다(fallback id로도 fetched_ok는 통과하므로 resolve 현행성 자체를 증명하진 않음; resolve 현행성은 search-first가 자동 동적 갱신).
  - ★시행규칙 별표 1건(13,213자)은 size-tier 예산(15,700) 미만 → 본문 전문 tier-1. oversized 강등 없음(별도 acceptance 항목 없음·필요 시 get_provision_detail 수동 확인).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

# 신규 학술진흥법 3건(도달성) + 기존 대형/대표 규정(무회귀) — id는 rule_sets.yaml 기준
_HAKJIN_REGS = [
    "hakjin_act",
    "hakjin_decree",
    "hakjin_rule",
]
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "신규 도달성 — 학술진흥법 3건이 fan-out에서 오류 없이 조회 + '학술진흥' 질의 결과 반환",
        "tool": "search_provision",
        "args": {"query": "학술진흥"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _HAKJIN_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 1}]                            # 결과 반환 net (block 후보)
        ),
    },
    {
        "name": "신규 도달성 — 학술연구지원사업 절차어('연구부정' 등)로 학술진흥법 시행령 도달",
        "tool": "search_provision",
        "args": {"query": "학술연구지원"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "hakjin_decree"},   # 도달(block 후보)
        ],
    },
    {
        "name": "무회귀 — 광역 '연구개발비' 도달·recall(학술진흥법 확대가 기존 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]
            + [{"kind": "returned_not_below", "value": 5}]
        ),
    },
    {
        "name": "skip·latency 모니터 — N=39 cold tail 허용(WARN only). 확대가 평소 경로를 안 깼는지",
        "tool": "search_provision",
        "args": {"query": "협약 변경"},
        "asserts": [
            {"kind": "absent_error_code", "value": "timeout"},   # WARN — 비결정 skip 허용(정상 cold tail)
            {"kind": "latency_under", "value": 16.0},            # WARN — cold tail 변동 허용
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인) — 호스트 LLM 행동(비결정). 게이트 판정은 사람.
LEVEL_B_PROMPTS = [
    {
        "category": "hakjin-coverage",
        "probe_prompt": "학술진흥법상 학술연구지원사업의 대상자 선정·협약·사업비(출연금) 관리 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "학술진흥법 시행령(선정 제6조·협약 제7조·사업비 지급 제8조·결과 평가 제10조 등)을 도구로 조회해 근거 조문(provision_id) 인용. "
                           "교육부 학술진흥법 family가 검토 대상에 포함됨(범위 밖 오분류 안 함). 외부 law.go.kr로 우회하지 않고 get_provision_detail content로 본문 확인.",
    },
    {
        "category": "cross-law-framing",
        "probe_prompt": "학술진흥법에 따른 학술연구지원사업이 국가연구개발혁신법의 적용을 받는지, 두 법의 관계를 규정 근거와 함께 정리해줘",
        "expect_behavior": "학술진흥법과 혁신법을 각각 도구로 조회해 적용 범위를 구분 인용. 일반법(혁신법) vs 개별법 우선순위를 사안 특성에 따라 신중히 다루고, "
                           "근거 없이 한쪽이 전면 적용된다고 단정하지 않음.",
    },
    {
        "category": "scope-honesty-stale",
        "probe_prompt": "(미지원 가능) 교육부 '이공분야 학술연구지원사업 처리규정'의 현행 고시번호와 시행일을 알려줘",
        "expect_behavior": "본 서버 39개 규정 밖(OpenAPI 미수록 행정규칙일 수 있음)이면 본 서버 근거로 확인되지 않았음을 밝히고, 고시번호·시행일을 현행으로 단정하지 말고 "
                           "1차 출처(국가법령정보센터) 확인을 권함(미지원 규정 stale 식별자 단정 자제 가드).",
    },
]
