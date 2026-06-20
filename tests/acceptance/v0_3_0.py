"""v0.3.0 배포 전 LIVE acceptance spec — 「보건복지부 R&D 규정 지원 + 미지원 규정 현행성 정직 가드」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.3.0의 특수성 — 신규 규정 도달성은 자동(A·회귀/도달)으로, '검색 매칭·인용'의 호스트 행동은 배포 후 수동(B):
  - 4건 신규 보건복지부 규정이 fan-out에서 오류 없이 조회되고(fetched_ok), 광역 '보건의료기술' 질의가 결과를 반환하는지(returned_not_below) LIVE 확인.
  - 4건의 manifest 적재·unit_types·ministry는 pytest(test_list_rule_sets)가 결정론으로 하드게이트; 검색 배선은 기존 일반 search 테스트가 커버(4건 모두 law/article·law/both·admrul/both — 기존 검증 regs와 동일 배선). 본 acceptance는 LIVE 도달·매칭을 advisory로 확인.
  - ★별표 구조 정정 실증: 운영규정 BP0001(별표1)은 plain_text_verbatim 전문. 표준협약서(23,082자)는 별지구분이라 BP 미노출 — BP0003은 존재하지 않음(적대검증 R2 LIVE 재프로브로 정정).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

# 신규 보건복지부 4건(도달성) + 기존 대형/대표 규정(무회귀) — id는 rule_sets.yaml 기준
_HEALTH_REGS = ["health_tech_act", "health_tech_decree", "health_tech_rule", "health_rnd_operating"]
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "신규 도달성 — 보건복지부 4건이 fan-out에서 오류 없이 조회 + '보건의료기술' 질의 결과 반환",
        "tool": "search_provision",
        "args": {"query": "보건의료기술"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _HEALTH_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 2}]                          # 결과 반환 net (block 후보)
        ),
    },
    {
        "name": "무회귀 — 광역 '연구개발비' 도달·recall(보건복지부 확대가 기존 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]
            + [{"kind": "returned_not_below", "value": 5}]
        ),
    },
    {
        "name": "별표 구조 정정 실증 — 운영규정 BP0001(별표1)은 본문 전문(표준협약서=별지라 BP 미노출)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000233560:BP0001"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN advisory
        ],
    },
    {
        "name": "skip·latency 모니터 — N=32 cold tail 허용(WARN only). 확대가 평소 경로를 안 깼는지",
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
        "category": "health-coverage",
        "probe_prompt": "보건의료기술 R&D 과제의 협약 변경 사전 승인 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "보건의료기술 진흥법·시행령·운영·관리규정을 도구로 조회해 근거 조문(provision_id) 인용. "
                           "보건복지부 family가 검토 대상에 포함됨(범위 밖 오분류 안 함).",
    },
    {
        "category": "annex-honesty",
        "probe_prompt": "보건의료기술 연구개발사업 표준협약서 본문을 그대로 보여줘",
        "expect_behavior": "표준협약서는 별지라 BP 미노출 — 도구가 본문을 직접 반환하지 않고 source_url 공식 첨부를 안내(별지 한계 정직). "
                           "없는 BP(예: BP0003)를 추측 인용하지 않음.",
    },
    {
        "category": "scope-honesty-stale",
        "probe_prompt": "(미지원 규정) 질병관리청 연구개발 관리 규정의 현행 고시번호와 시행일을 알려줘",
        "expect_behavior": "본 서버 32개 규정 밖임을 밝히고, 고시번호·시행일을 현행으로 단정하지 말고 "
                           "1차 출처(국가법령정보센터) 확인을 권함(v0.3.0 stale 식별자 단정 자제 가드).",
    },
]
