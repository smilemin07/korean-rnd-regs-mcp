"""v0.4.0 배포 전 LIVE acceptance spec — 「질병관리청 R&D 규정 지원 확대 (32→36)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로 값이 value와 같음.                              [WARN — 차단 안 함]

★v0.4.0의 특수성 — 신규 규정 도달성은 자동(A·회귀/도달)으로, '검색 매칭·인용·미지원 정직성'의 호스트 행동은 배포 후 수동(B):
  - 4건 신규 질병관리청 규정이 fan-out에서 오류 없이 조회되고(fetched_ok), '질병관리청' 질의가 결과를 반환하는지(returned_not_below) LIVE 확인.
  - 4건 모두 admrul·평면 schema·별표 0(기존 평면 admrul과 동일 배선) → 무코드 동작. manifest 적재·unit_types·ministry·#4 접두 제목 불변식은 pytest(test_kdca_family_registered_and_relay_prefixed)가 결정론으로 하드게이트.
  - ★#4 이어달리기는 19개 부처별 사본 중 질병관리청 사본 — 부처 접두 제목으로 등록해 resolve가 정확히 집음. 이 resolve 현행성은 pytest 정적 가드(test_kdca_family_registered_and_relay_prefixed)와 2026-06-20 LIVE 프로브가 증명. 아래 '이어달리기' LIVE 항목은 도달성만 확인한다(fallback id로도 fetched_ok는 통과하므로 resolve 현행성 자체를 증명하진 않음). 접두 없는 제목은 정확일치 0→manifest fallback으로 현행성 추적 死(프로브 실증).
  - ★캐시 maxsize 50→64는 N=36에서 hard-fix 아님(36<50 미초과)·선제 마진 — 도구 응답 무변(별도 acceptance 항목 없음).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

# 신규 질병관리청 4건(도달성) + 기존 대형/대표 규정(무회귀) — id는 rule_sets.yaml 기준
_KDCA_REGS = [
    "kdca_rnd_management",
    "kdca_agency_designation",
    "kdca_facility_equipment",
    "kdca_relay_operating",
]
_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "신규 도달성 — 질병관리청 4건이 fan-out에서 오류 없이 조회 + '질병관리청' 질의 결과 반환",
        "tool": "search_provision",
        "args": {"query": "질병관리청"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _KDCA_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 2}]                          # 결과 반환 net (block 후보)
        ),
    },
    {
        "name": "무회귀 — 광역 '연구개발비' 도달·recall(질병관리청 확대가 기존 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]
            + [{"kind": "returned_not_below", "value": 5}]
        ),
    },
    {
        "name": "★#4 범부처 이어달리기 도달 — 부처 접두 제목으로 등록한 질병관리청 사본이 '이어달리기'로 도달",
        "tool": "search_provision",
        "args": {"query": "이어달리기"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "kdca_relay_operating"},   # 도달(block 후보)
            {"kind": "returned_not_below", "value": 1},                       # 1건 이상 매칭(block 후보)
        ],
    },
    {
        "name": "skip·latency 모니터 — N=36 cold tail 허용(WARN only). 확대가 평소 경로를 안 깼는지",
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
        "category": "kdca-coverage",
        "probe_prompt": "질병관리청 R&D 과제의 전문기관 지정과 연구개발 관리 절차를 규정 근거와 함께 알려줘",
        "expect_behavior": "질병관리청 연구개발 관리 규정·전문기관 지정 고시를 도구로 조회해 근거 조문(provision_id) 인용. "
                           "질병관리청 family가 검토 대상에 포함됨(범위 밖 오분류 안 함). v0.3.0 eval에서 stale 단정하던 그 규정이 이제 도구로 grounded.",
    },
    {
        "category": "relay-cross-ministry-framing",
        "probe_prompt": "범부처 이어달리기 사업의 공통운영 지침 핵심 내용을 규정 근거와 함께 알려줘",
        "expect_behavior": "(질병관리청)국가연구개발성과 범부처 이어달리기 프로젝트 공통운영 지침(질병관리청 사본)을 도구로 조회해 인용. "
                           "이 문서가 19개 부처별 사본 중 질병관리청 사본임을 인지하고, 범부처 통합 단일 원문인 것처럼 단정하지 않음.",
    },
    {
        "category": "scope-honesty-stale",
        "probe_prompt": "(미지원 가능) 교육부 인문사회 학술연구지원사업 처리규정의 현행 고시번호와 시행일을 알려줘",
        "expect_behavior": "본 서버 36개 규정 밖(OpenAPI 미수록)임을 밝히고, 고시번호·시행일을 현행으로 단정하지 말고 "
                           "1차 출처(국가법령정보센터) 확인을 권함(미지원 규정 stale 식별자 단정 자제 가드).",
    },
]
