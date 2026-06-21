"""v0.5.0 배포 전 LIVE acceptance spec — 「행정규칙 version 메타데이터 내재화 (발령번호·종류 노출)」.

읽는 법(비프로그래머용): 아래 CHECKS는 '이번 버전 변경이 살아있고 기존 동작을 회귀시키지 않았는지' LIVE로 확인할 항목입니다.
각 항목 = {이름, 도구, 인자, 검증}. 검증(asserts) 종류는 5가지로 고정(run.py):
  - fetched_ok        : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달).                  [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                          [회귀=BLOCK 후보]
  - absent_error_code : 지정 오류코드가 0건.                                            [WARN — 차단 안 함]
  - latency_under     : 응답이 value초 미만.                                            [WARN — 차단 안 함]
  - field_equals      : 응답의 특정 경로(path) 값이 value와 같음.                        [WARN — 차단 안 함]

★v0.5.0의 특수성 — version 필드 '존재·합성'은 pytest가 결정론으로 하드게이트(test_*_includes_version_meta_v050,
  test_admrul_version_meta_*_v050, B1 source 정합은 19건 LIVE 프로브로 확정, B2 size는
  test_version_meta_injection_within_annex_headroom_v050 + 아래 LIVE size 수동 스모크). 아래 LIVE CHECKS는
  배포 직전 신코드가 실제 law.go.kr 대상으로 version_label을 정확히 합성하는지(field_equals=WARN, LIVE 증명)와
  기존 검색 무회귀(fetched_ok/returned_not_below=BLOCK 후보)를 확인한다.
  - get_provision_detail("admrul:2100000214227")=질병관리청 시설·장비 관리 규정(예규 106호·2022 제정·일련번호 안정)
    → manifest 직접매칭으로 항상 해당 rule set 조회. version_label="예규 제106호"·regulation_kind="예규" LIVE 합성 확인.
  - ★B2 LIVE size 수동 스모크(러너 자동 아님): 배포 직전 표준지침 oversized 별표(admrul:<현행 일련번호>:BP0013 등)
    응답에 version 필드가 실려도 직렬화가 _ANNEX_DETAIL_CHAR_BUDGET(16000)을 넘지 않는지 1회 육안 확인.
  - law은 version 필드 미주입 — pytest(test_law_doc_level_has_no_version_meta_v050)가 가드(acceptance 항목 없음).

새 버전 만들 때: 이 파일을 복사해 CHECKS/LEVEL_B_PROMPTS만 그 버전에 맞게 바꾸면 됩니다.
"""

_BIG_REGS = ["ict_rnd_management", "innovation_decree", "rnd_funding_standard"]

CHECKS = [
    {
        "name": "version 메타 LIVE — 질병청 시설·장비 규정(예규 106호) doc-level version_label·regulation_kind 합성",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000214227"},   # kdca_facility_equipment(예규 106호·안정)
        "asserts": [
            {"kind": "field_equals", "path": "regulation_kind", "value": "예규"},        # WARN — LIVE 종류 합성
            {"kind": "field_equals", "path": "version_label", "value": "예규 제106호"},   # WARN — LIVE 라벨 합성
        ],
    },
    {
        "name": "version 메타 LIVE — 표준지침(고시 2026-25호) doc-level version_label 합성(연도형 번호)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000278230"},   # facility_equipment_standard(표준지침·고시 2026-25호)
        "asserts": [
            {"kind": "field_equals", "path": "regulation_kind", "value": "고시"},          # WARN
            {"kind": "field_equals", "path": "version_label", "value": "고시 제2026-25호"},  # WARN — 연도형 합성
        ],
    },
    {
        "name": "무회귀 — 광역 '연구개발비' 도달·recall(version 메타 추가가 기존 검색을 안 깸)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": (
            [{"kind": "fetched_ok", "rule_set_id": rid} for rid in _BIG_REGS]   # 도달 net (block 후보)
            + [{"kind": "returned_not_below", "value": 5}]                       # recall net (block 후보)
        ),
    },
    {
        "name": "skip·latency 모니터 — N=36 cold tail 허용(WARN only). 파싱 추가가 평소 경로를 안 깼는지",
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
# v0.4.1 eval에서 FAIL이던 프롬프트 2·3·4를 재실행해 발령번호 도구 제공으로 외부-first·stale·false-negative가 해소됐는지 확인.
LEVEL_B_PROMPTS = [
    {
        "category": "single-issuance-number (v0.4.1 프롬프트2)",
        "probe_prompt": "질병관리청 연구개발 관리 규정의 현행 예규 번호와 시행일을 공문에 쓰게 정확히 알려줘",
        "expect_behavior": "get_provision_detail를 호출해 응답의 version_label('예규 제179호')·regulation_kind·effective_date로 답함. "
                           "발령번호를 얻으려 외부 web을 헤매지 않음(도구가 직접 제공). v0.4.1에선 외부 시도하다 정직 미확인이던 경로.",
    },
    {
        "category": "compare-number-first (v0.4.1 프롬프트3 SEVERE FAIL)",
        "probe_prompt": "질병관리청 시설·장비 관리 규정과 국가연구개발 시설·장비 표준지침의 현행 고시·예규 번호와 시행일을 먼저 정리하고, 두 규정의 차이를 조문 근거로 비교해줘",
        "expect_behavior": "★핵심 회귀 — '번호 먼저' framing에도 호스트가 외부-first로 가지 않고 두 규정을 get_provision_detail로 조회해 "
                           "version_label(예규 제106호·고시 제2026-25호)·시행일을 도구 응답에서 인용. "
                           "★등록된 kdca_facility_equipment를 '존재하지 않음'으로 false-negative 단정하지 않음(v0.4.1 SEVERE FAIL 해소 확인). "
                           "stale 번호(2025-46호·122호) 미출현.",
    },
    {
        "category": "oversized-annex-version (v0.4.1 프롬프트4 FAIL)",
        "probe_prompt": "표준지침의 대용량 별표 본문과 그 규정의 현행 고시번호·시행일을 알려줘",
        "expect_behavior": "현행 version 식별자(version_label '고시 제2026-25호'·시행일)는 도구 응답에서 정확히 제공(외부 stale 2025-46호 미단정). "
                           "단 oversized 별표 '본문'은 도구가 여전히 미수록 — 공식 원문 링크(document_source_url) 안내(본문은 v0.5.0 범위 밖, "
                           "'현행 version 식별자 제공'까지가 목표).",
    },
]
