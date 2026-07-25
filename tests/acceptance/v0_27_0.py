"""v0.27.0 배포 전 LIVE acceptance spec — 「R1 혁신법 매뉴얼 트랙 — 도구 2종·contract 0.18.0·프롬프트 가드」.

읽는 법(비프로그래머용): 이번 v0.27.0은 R1 매뉴얼 트랙 릴리스입니다 — 신규 도구 2종
(search_manual·get_manual_section·패키지 동봉 로컬 데이터·네트워크 0)과 프롬프트 가드(매뉴얼 라우팅·
하단 표준 안내)가 추가되고, 기존 5종 도구·계약 §5.1~5.18은 무접촉입니다. Level A(자동)는
① 기존 무회귀(자율주행 검색 도달·별표 tier-1·기본 경로 oversized_pointer·청크·recall)와
② 매뉴얼 신규 기능의 결정론 확인(절 도달·전문/포인터/청크·규범성 메타 notice)을 수행합니다.
매뉴얼 도구는 로컬 데이터라 LIVE 변동이 없으며, 실패는 패키징·로더 회귀 신호입니다.
개선의 핵심(호스트가 매뉴얼을 해설로만 쓰고 법령 우선·하단 안내를 표시)은 호스트 LLM 행동(Level B)이라
배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★매뉴얼 체크는 전부 WARN 클래스(신규 기능 — 무회귀 BLOCK 대상 아님·false-block-safe).
  BLOCK 후보는 기존 검색 무회귀에만. ★주의: runner의 hard-BLOCK assert(fetched_ok·
  returned_not_below)는 search_provision 응답(results) 전용이라 매뉴얼 체크는 구조적으로
  WARN 증거임 — 매뉴얼 기능의 hard gate는 pytest(test_manual_tools.py 29건)가 담당.
"""

CHECKS = [
    {
        "name": "무회귀 A — 자율주행 검색 도달 유지('자율주행' 무접두 fan-out — v0.26.0 신규 승계)",
        "tool": "search_provision",
        "args": {"query": "자율주행"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "kt_autonomous_driving"},                   # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
        ],
    },
    {
        "name": "무회귀 B — 자율주행 별표 3 tier-1 유지(admrul:2100000282292:BP0003)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000282292:BP0003"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 C — 기본 경로 무변(law:285767:BP0002 opt-in 미지정 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(신규 도구 추가가 기존 검색 경로 무해)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN
        ],
    },
    {
        "name": "★신규 A — search_manual '기술료' 제목 매치 최상위(2-6)·규범성 notice",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "absent_error_code", "value": "manual_unavailable"},                     # WARN — 패키징·로더
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "2-6"},         # WARN — 3단 정렬
            {"kind": "field_equals", "path": "manual_meta.legal_effect", "value": "not_binding"},  # WARN — 규범성 메타
            {"kind": "field_equals", "path": "manual_meta.notice",
             "value": "인용 매뉴얼: 26.4판 · 법령 시행일 2026-03 기준"},                        # WARN — notice 완성형
        ],
    },
    {
        "name": "★신규 B — search_manual 0건 결정론 앵커(scanned_sections=41)",
        "tool": "search_manual",
        "args": {"query": "존재하지않는키워드검증용문자열"},
        "asserts": [
            {"kind": "field_equals", "path": "scanned_sections", "value": 41},                # WARN — 전수 스캔 앵커
            {"kind": "field_equals", "path": "total_matched", "value": 0},                    # WARN
        ],
    },
    {
        "name": "★신규 C — get_manual_section 소형 절 전문(3-9 보안수당 verbatim)",
        "tool": "get_manual_section",
        "args": {"section_id": "3-9"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "is_complete", "value": True},                   # WARN
            {"kind": "field_equals", "path": "page_start", "value": 243},                     # WARN — 인쇄쪽 앵커
        ],
    },
    {
        "name": "★신규 D — get_manual_section 대형 절 포인터(2-3 협약 — oversized_pointer+chunk 안내)",
        "tool": "get_manual_section",
        "args": {"section_id": "2-3"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN
            {"kind": "field_equals", "path": "content_available", "value": False},            # WARN
            {"kind": "field_equals", "path": "chunk_count", "value": 3},                      # WARN — P2 실측 3청크
        ],
    },
    {
        "name": "★신규 E — get_manual_section 청크 조회(2-3 chunk=1 — verbatim·인쇄쪽 범위)",
        "tool": "get_manual_section",
        "args": {"section_id": "2-3", "chunk": 1},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "is_complete", "value": False},                  # WARN
            {"kind": "field_equals", "path": "chunk_pages.page_start", "value": 63},          # WARN — P2 실측
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.27.0 = 매뉴얼 해설 실효 + 규범성 가드 + 하단 표준 안내.
LEVEL_B_PROMPTS = [
    {
        "category": "★신규 — 매뉴얼 해설 실효 + 하단 표준 안내 부착(A-1/A-2/notice 3종 관측)",
        "probe_prompt": "연구활동비로 회의비를 쓸 때 증명자료로 뭘 갖춰야 하는지, 혁신법 매뉴얼 해설도 함께 확인해서 실무 기준으로 정리해줘.",
        "expect_behavior": "search_manual/get_manual_section으로 매뉴얼 3-7(연구활동비 증명자료 — 매뉴얼 고유 실무표) "
                           "해설을 활용하고 + 법령·행정규칙 근거(연구개발비 사용 기준)를 병행 확인하는지. 매뉴얼 내용은 "
                           "해설임을 구분 표시(판번·인쇄쪽 앵커)하는지. ★핵심 관측 3종: 답변 하단에 A-1(국가법령정보센터 "
                           "기준 확인)·A-2(매뉴얼은 법령·행정규칙이 아니며 법령 우선)·notice(인용 매뉴얼: 26.4판…) 가 "
                           "각 1회, 요약·윤문 없이 그대로 부착되는지. 자체 면책문 중복 생성이 없는지.",
    },
    {
        "category": "★신규 — 규범성 혼동 방지(매뉴얼 근거 면책 기대 차단·법령 우선)",
        "probe_prompt": "혁신법 매뉴얼 해설에 어떤 비목 사용이 예외적으로 허용된다는 취지의 설명이 있으면, 시행령이나 연구개발비 사용 기준 고시에 명시적 제한이 있어도 매뉴얼을 근거로 집행해도 되는 건가? 제재 시 매뉴얼 해설을 면책 근거로 쓸 수 있어?",
        "expect_behavior": "매뉴얼은 해설 자료(법령·행정규칙 아님·legal_effect=not_binding)이며 법령·행정규칙 원문이 "
                           "우선한다는 결론을 명확히 제시하는지. 매뉴얼을 규범적 면책 근거로 단정하지 않는지. "
                           "법령·고시 원문 확인(규정 도구)을 안내하는지. 하단 표준 안내 부착 여부 동시 관측. "
                           "★관측 한계: 가정형 질의라 실제 불일치 사례 재현은 아님 — 호스트가 실존하지 않는 "
                           "불일치 사례·조문을 임의로 만들어 예시하면 그 자체가 감점(날조) 관측 대상.",
    },
    {
        "category": "무회귀 — 라우팅 격리(조문 원문 질의에 매뉴얼 오염 0)",
        "probe_prompt": "국가연구개발혁신법 제13조 조문 원문을 보여줘.",
        "expect_behavior": "기존 규정 도구(get_provision_detail)로 조문 원문을 verbatim 제공하는지. 매뉴얼 도구를 "
                           "불필요하게 호출하거나 매뉴얼 해설을 조문 원문에 혼입하지 않는지(혼입 0). 원문 답변 품질이 "
                           "v0.26.1 수준에서 회귀하지 않는지. A-1 하단 안내 1회 부착 관측.",
    },
]
