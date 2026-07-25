"""v0.28.0 배포 전 LIVE acceptance spec — 「매뉴얼 인용 앵커·하단 안내 응답 구조화」.

읽는 법(비프로그래머용): 이번 v0.28.0은 매뉴얼 도구 2종의 응답에 완성형 인용구(citation)와
완성형 하단 안내(standard_footer)를 추가한 릴리스입니다. 서버가 이미 갖고 있던 값(인쇄쪽·판번)을
다시 조립해 문자열로 내보내는 것이라 추가 조회·신규 파싱이 없고, 기존 5종 규정 도구는 무접촉입니다.
Level A(자동)는 ① 기존 무회귀(검색 도달·별표 tier-1·기본 경로 oversized_pointer·recall)와
② 신규 필드의 결정론 확인(citation 문자열·footer 3줄/1줄 분기·size-tier 무회귀)을 수행합니다.
개선의 핵심(호스트가 citation을 실제로 인용하고 footer를 그대로 부착하는가)은 호스트 LLM 행동
(Level B)이라 배포 후 라이브 커넥터에서 사람이 LEVEL_B_PROMPTS로 수동 확인합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨(도달=errors에 없음).           [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                         [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음.                            [WARN — 차단 안 함]

★매뉴얼 체크는 전부 WARN 클래스(로컬 데이터 — LIVE 변동 없음·false-block-safe). 매뉴얼 기능의
  hard gate는 pytest(test_manual_tools.py 41건)가 담당하고, 여기서는 배포 이미지에서도 동일 문자열이
  나오는지(패키징·로더 회귀 신호)를 증거로 남깁니다. BLOCK 후보는 기존 검색 무회귀에만.
"""

CHECKS = [
    {
        "name": "무회귀 A — 자율주행 검색 도달 유지('자율주행' 무접두 fan-out)",
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
        "name": "무회귀 C — 기본 경로 무변(law:285767:BP0002 → oversized_pointer 유지)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:285767:BP0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                              # WARN
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN
            {"kind": "field_equals", "path": "verbatim_quote_allowed", "value": False},       # WARN
        ],
    },
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(응답 필드 추가가 기존 검색 경로 무해)",
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
        "name": "★신규 A — search_manual 매치별 citation 완성형(2-6 기술료·판번+장절+인쇄쪽)",
        "tool": "search_manual",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "absent_error_code", "value": "manual_unavailable"},                     # WARN — 패키징·로더
            {"kind": "field_equals", "path": "matches.0.section_id", "value": "2-6"},         # WARN — 3단 정렬 무회귀
            {"kind": "field_equals", "path": "matches.0.citation",
             "value": "「국가연구개발혁신법 매뉴얼(본권)」(26.4판) 제2장 제6절 기술료 징수･납부･사용, 인쇄 p.107~113"},  # WARN
        ],
    },
    {
        "name": "★신규 B — 매뉴얼 해설 전달 시 하단 안내 3줄(검색 매치 존재)",
        "tool": "search_manual",
        "args": {"query": "학생인건비"},
        "asserts": [
            {"kind": "field_equals", "path": "manual_meta.standard_footer",
             "value": ("※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 법령·행정규칙 원문을 기준으로 해주시기 바랍니다.\n"
                       "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
                       "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다.\n"
                       "※ 인용 매뉴얼: 26.4판 · 법령 시행일 2026-03 기준")},                   # WARN — 완성형 3줄
        ],
    },
    {
        "name": "★신규 C — 검색 0건은 법령 확인 1줄만(매뉴얼 미전달 → 허위 출처 고지 차단)",
        "tool": "search_manual",
        "args": {"query": "존재하지않는키워드검증용문자열"},
        "asserts": [
            {"kind": "field_equals", "path": "total_matched", "value": 0},                    # WARN
            {"kind": "field_equals", "path": "scanned_sections", "value": 41},                # WARN — 전수 스캔 앵커
            {"kind": "field_equals", "path": "manual_meta.standard_footer",
             "value": "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 법령·행정규칙 원문을 기준으로 해주시기 바랍니다."},  # WARN
        ],
    },
    {
        "name": "★신규 D — 소형 절 전문: citation=절 범위 + size-tier 무회귀(3-9)",
        "tool": "get_manual_section",
        "args": {"section_id": "3-9"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — tier 무회귀
            {"kind": "field_equals", "path": "is_complete", "value": True},                   # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가연구개발혁신법 매뉴얼(본권)」(26.4판) 제3장 제9절 보안수당 사용용도 및 사용기준, 인쇄 p.243~244"},  # WARN
        ],
    },
    {
        "name": "★신규 E — 포인터는 본문 미전달 → 하단 안내 1줄(2-3)",
        "tool": "get_manual_section",
        "args": {"section_id": "2-3"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "oversized_pointer"},  # WARN — tier 무회귀
            {"kind": "field_equals", "path": "chunk_count", "value": 3},                      # WARN
            {"kind": "field_equals", "path": "manual_meta.standard_footer",
             "value": "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 법령·행정규칙 원문을 기준으로 해주시기 바랍니다."},  # WARN
        ],
    },
    {
        "name": "★신규 F — 청크 citation은 그 청크의 인쇄쪽 범위(절 전체로 넓히지 않음·2-3 chunk=1)",
        "tool": "get_manual_section",
        "args": {"section_id": "2-3", "chunk": 1},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "chunk_pages.page_start", "value": 63},          # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「국가연구개발혁신법 매뉴얼(본권)」(26.4판) 제2장 제3절 연구개발과제의 협약, 인쇄 p.63~70"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 커넥터 + 사람 확인). ★v0.28.0 = 인용 앵커·하단 안내의 실제 발현율.
# 직전 v0.27.0 eval에서 인쇄쪽 인용 0/3·하단 안내 0/3이었으므로, 같은 축을 서버 완성형 제공
# 상태에서 재관측한다(개선 여부의 직접 측정).
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — citation 인쇄쪽 인용 발현(직전 0/3 축)",
        "probe_prompt": "학생인건비를 다른 기관에서 이미 받고 있는 학생연구자에게 우리 과제에서 얼마나 지급할 수 있는지, 경계 사례까지 포함해서 알려줘.",
        "expect_behavior": "매뉴얼 도구를 호출해 3-4절 해설로 답하는지(직전 관측: 자연 라우팅 HIT). ★핵심 관측: "
                           "매뉴얼 근거를 제시할 때 응답의 citation 값(「…매뉴얼(본권)」(26.4판) 제3장 제4절 …, 인쇄 p.200~218)을 "
                           "그대로 표기하는지 — 판번만 인용하고 인쇄쪽을 빠뜨리던 직전 결함이 해소됐는지. "
                           "청크를 조회한 경우 절 전체 범위가 아니라 그 청크의 인쇄쪽으로 표기하는지.",
    },
    {
        "category": "★표적 — 하단 표준 안내 블록 부착 발현(직전 0/3 축)",
        "probe_prompt": "회의비로 식비를 쓸 때 사전결재를 꼭 받아야 하는지, 실무 기준으로 정리해줘.",
        "expect_behavior": "매뉴얼 3-7 해설 + 법령(연구개발비 사용 기준) 병행 확인. ★핵심 관측: 답변 마지막에 "
                           "standard_footer 3줄(법령 원문 기준 확인 / 매뉴얼 해설 고지 / 인용 매뉴얼 판번·기준일)이 "
                           "요약·윤문 없이 그대로, 1회만 부착되는지. 자체 면책문을 따로 만들어 중복 부착하지 않는지.",
    },
    {
        "category": "무회귀 — 매뉴얼 미사용 답변에 매뉴얼 고지 오부착 0",
        "probe_prompt": "국가연구개발혁신법 제13조 조문 원문을 보여줘.",
        "expect_behavior": "기존 규정 도구로 조문 원문 verbatim 제공(매뉴얼 도구 미호출). ★핵심 관측: 매뉴얼을 쓰지 "
                           "않았으므로 하단에 A-1(법령 원문 기준 확인) 1줄만 붙고 '매뉴얼 해설 부분은…' 문구가 "
                           "오부착되지 않는지. 조문 원문 품질이 v0.27.0 수준에서 회귀하지 않는지.",
    },
]
