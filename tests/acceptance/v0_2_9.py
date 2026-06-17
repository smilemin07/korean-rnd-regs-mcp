"""v0.2.9 배포 전 LIVE acceptance spec — 「규정 질의 도구 호출 유도 — 메타데이터 가드」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts)은 코드가 아니라 데이터이며, 종류는 5가지로 고정:
  - fetched_ok      : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                              [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                                     [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드(예: timeout)가 0건.                                            [WARN — 차단 안 함]
  - latency_under   : 응답이 value초 미만.                                                          [WARN — 차단 안 함]
  - field_equals    : 응답의 특정 경로 값이 value와 같음.                                            [WARN — 차단 안 함]

★v0.2.9의 특수성 — 검증 무게중심이 자동(A)에서 수동(B)으로 넘어간다:
  - v0.2.9 변경은 서버 instructions + 도구 docstring + 가드 테스트 = '메타데이터(텍스트)'뿐이며,
    search_provision의 검색·랭킹·응답 로직을 전혀 바꾸지 않는다. 따라서 아래 Level A CHECKS는
    '기능 증명'이 아니라 순수 '회귀 가드'다 — 광역 '연구개발비' 최상위·대형 규정 도달·recall이
    v0.2.8 그대로인지(=메타데이터 편집이 검색을 안 깼는지)만 확인한다.
  - 이 릴리스의 진짜 가치('호스트가 규정 질의에 도구를 *부르는가*' + '과호출을 안 하는가')는
    이 하니스가 도구를 *직접* 호출하므로 관측 불가(호스트를 건너뜀) → 배포 후 사람이 진짜
    호스트(Claude.ai 웹·Claude Desktop·ChatGPT)에서 LEVEL_B_PROMPTS로 수동 eval한다(게이트 판정 아님).

새 버전 만들 때: 이 파일을 복사해 v0_2_10.py 등으로 두고 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

# 대형 규정(메타데이터 편집이 도달·recall을 회귀시키지 말아야 할 것) — id는 rule_sets.yaml 기준
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "검색 불변 회귀 가드 — 광역 '연구개발비' 최상위·매몰 규정 생존(v0.2.8 동작 유지)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 5}]                       # recall net (block 후보)
            # ★관련도 advisory(WARN): 문서 제목이 '연구개발비'를 직접 가진 규정이 최상위 유지인지
            #   (메타데이터 변경이 v0.2.8 정렬을 안 깼음을 실증; LIVE cold 변동 가능 → WARN).
            + [{"kind": "field_equals", "path": "results.0.rule_set_id", "value": "rnd_funding_standard"}]
        ),
    },
    {
        "name": "핀포인트 비회귀 — '기술료'(ministry 필터 수혜 규정) 도달",
        "tool": "search_provision",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "tech_fee_integrated"},
            {"kind": "returned_not_below", "value": 5},
        ],
    },
    {
        "name": "skip·latency 모니터 — 정상 cold tail 변동 허용(WARN only)",
        "tool": "search_provision",
        "args": {"query": "간접비"},
        "asserts": [
            {"kind": "absent_error_code", "value": "timeout"},   # WARN — 비결정 skip 허용
            {"kind": "latency_under", "value": 16.0},            # WARN — cold tail 변동 허용
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
        ],
    },
]

# Level B(호스트 LLM 행동) — 배포 후 라이브 커넥터에서 사람이 수동 확인(게이트 판정 아님).
# ★v0.2.9 핵심 검증: positive=규정 질의에 도구를 *부르는가* / negative=범위 밖 질의에 *안 부르는가*(과호출 차단).
# 측정: any MCP tool-call 여부·첫 호출 도구·근거 조항 인용·soft-fabrication 수·negative 과호출 여부.
# 통과 기준(advisory, hard gate 아님): Claude.ai positive 호출률 ≥70%·원 실패 프롬프트 "연구개발비 폭넓게
#   알려줘" 3회 중 ≥2회 호출·negative 과호출 ≤1/3·soft-fabrication 0.
LEVEL_B_PROMPTS = [
    # --- positive (도구 호출 기대) ---
    {
        "category": "positive",
        "probe_prompt": "연구개발비 폭넓게 알려줘",
        "expect_behavior": "호스트가 일반 학습지식으로 단정하지 말고 search_provision/suggest_review_sources를 "
                           "호출해 LIVE 규정(연구개발비 사용 기준 등)을 근거로 답함. v0.2.8 eval에서 미호출(soft-fab)이던 그 프롬프트.",
    },
    {
        "category": "positive",
        "probe_prompt": "국가연구개발혁신법 주요 내용 알려줘",
        "expect_behavior": "호스트가 도구를 호출해 혁신법 조문을 근거로 인용(광역 '알려줘' 표현도 호출 대상).",
    },
    {
        "category": "positive",
        "probe_prompt": "연구개발비 사용 기준 제30조 인력지원비 알려줘",
        "expect_behavior": "호스트가 get_provision_detail로 현행 원문을 확인 → 제30조가 현행 '삭제'임을 정직 반영"
                           "(훈련지식으로 활성 조문처럼 단정하지 않음). 삭제 여부·현행 내용 확인 유도의 검증점.",
    },
    # --- negative (도구 미호출 기대 — 과호출 차단 검증) ---
    {
        "category": "negative",
        "probe_prompt": "안녕하세요",
        "expect_behavior": "단순 인사 — 도구를 호출하지 않음.",
    },
    {
        "category": "negative",
        "probe_prompt": "이 문장 다듬어줘: 연구개발비를 집행하였습니다.",
        "expect_behavior": "순수 문장 다듬기 — '연구개발비'가 들어있어도 규정 사실 확인이 아니므로 도구를 호출하지 않음.",
    },
    {
        "category": "negative",
        "probe_prompt": "미국 NIH grant의 F&A costs 정책만 설명해줘. 한국 국가연구개발사업과 비교하지 마.",
        "expect_behavior": "본 서버 범위(대한민국 R&D 규정) 밖 해외 제도만의 설명 — 도구를 호출하지 않음.",
    },
]
