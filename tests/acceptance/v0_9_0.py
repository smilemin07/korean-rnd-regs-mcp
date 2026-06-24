"""v0.9.0 배포 전 LIVE acceptance spec — 「R&D 규정 지원 확대 2차 — 교육부 산학협력 family 3건 + 연구윤리 지침 (39 → 43)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.9.0의 특수성 — 순수 data(코드 무변경) 확대. 신규 규정 도달성은 자동(A·회귀/도달)으로, '검색 매칭·인용·미지원 정직성'의 호스트 행동은 배포 후 수동(B):
  - 4건 신규(산학협력 법·시행령·시행규칙 + 연구윤리 확보를 위한 지침)이 fan-out에서 오류 없이 조회되고(fetched_ok), '연구윤리' 질의가 결과를 반환하는지(returned_not_below) LIVE 확인.
  - 산학협력 3건은 law target·중첩 schema → 기존 law family와 동일 배선·무코드 동작. 연구윤리 지침은 admrul 평면 schema(기존 `_parse_flat_article` fallback 자동) → 무코드. manifest 적재·api_target·ministry·hierarchy는 pytest(test_sanhak_family_registered_v090)가 결정론으로 하드게이트.
  - ★LIVE 게이트(2026-06-24) 확정: 4건 전부 정확 title + ministry=교육부 정확일치 resolve가 유일 현행 문서 1건(트랙 충돌·동명이종·부처 사본 0·잘못된 부처 ministry 필터 격리 실증). 순수 yaml 데이터로 안전. 아래 LIVE 항목은 도달성만 확인한다(resolve 현행성은 search-first가 자동 동적 갱신).
  - ★시행규칙(285257) 부속문서 11건은 전부 별지서식(별표구분='서식')이라 BP 미노출 → unit_types=article·노출 별표 0. 시행령 별표1(BP0000·~1,856자)은 size-tier 예산(15,700) 미만 → 본문 전문 tier-1(oversized 강등 없음).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

# 신규 4건(도달성) + 기존 대형/대표 규정(무회귀) — id는 rule_sets.yaml 기준
_SANHAK_REGS = ["sanhak_act", "sanhak_decree", "sanhak_rule"]
_NEW_REGS = _SANHAK_REGS + ["research_ethics_guideline"]
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "신규 도달성 — 산학협력 family 3건 + 연구윤리 지침이 fan-out에서 오류 없이 조회",
        "tool": "search_provision",
        "args": {"query": "산학협력"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _NEW_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 1}]                          # 결과 반환 net (block 후보)
        ),
    },
    {
        "name": "신규 매칭 — '연구윤리' 질의로 연구윤리 확보 지침 도달 + 결과 반환",
        "tool": "search_provision",
        "args": {"query": "연구윤리"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "research_ethics_guideline"},   # 도달(block 후보)
            {"kind": "returned_not_below", "value": 1},
        ],
    },
    {
        "name": "무회귀 — 광역 '연구개발비' 도달·recall(산학협력·연구윤리 확대가 기존 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]
            + [{"kind": "returned_not_below", "value": 5}]
        ),
    },
    {
        "name": "skip·latency 모니터 — N=43 cold tail 허용(WARN only). 확대가 평소 경로를 안 깼는지",
        "tool": "search_provision",
        "args": {"query": "협약 변경"},
        "asserts": [
            {"kind": "absent_error_code", "value": "timeout"},   # WARN — 비결정 skip 허용(정상 cold tail)
            {"kind": "latency_under", "value": 16.0},            # WARN — cold tail 변동 허용(N=43)
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인) — 호스트 LLM 행동(비결정). 게이트 판정은 사람.
LEVEL_B_PROMPTS = [
    {
        "category": "sanhak-coverage",
        "probe_prompt": "산학협력단의 설립·운영과 기술지주회사 설립 요건을 산업교육진흥 및 산학연협력촉진법(시행령 포함) 근거와 함께 알려줘",
        "expect_behavior": "산학협력촉진법 family(법·시행령·시행규칙)를 도구로 조회해 근거 조문(provision_id)을 인용. "
                           "교육부 산학협력 규정이 검토 대상에 포함됨(범위 밖 오분류 안 함). 외부 law.go.kr로 우회하지 않고 get_provision_detail content로 본문 확인.",
    },
    {
        "category": "research-ethics",
        "probe_prompt": "국가연구개발사업에서 연구부정행위의 범위와 검증 절차(조사위원회 구성 등)를 규정 근거와 함께 정리해줘",
        "expect_behavior": "연구윤리 확보를 위한 지침(research_ethics_guideline)을 도구로 조회해 연구부정행위 범위·검증·조사위원회 조문을 인용. "
                           "평면 schema 특정 조문 식별이 필요하면 문서 레벨 articles 목록/search로 찾고, 외부 우회 없이 content로 확인.",
    },
    {
        "category": "scope-honesty-unsupported",
        "probe_prompt": "(미지원 가능) 교육부 '산학협력 선도대학(LINC) 사업 운영 매뉴얼'의 현행 세부 지원 기준을 알려줘",
        "expect_behavior": "OpenAPI 미수록 매뉴얼(PDF/HWP일 수 있음)이면 본 서버 43개 규정 밖임을 밝히고, 세부 기준·금액·비율을 현행으로 단정하지 말고 "
                           "1차 출처(국가법령정보센터 등) 확인을 권함(미지원 자료 stale 단정 자제).",
    },
]
