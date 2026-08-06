"""v0.40.0 배포 전 LIVE acceptance spec — 「검색·후보 경로 표준 안내 확대」.

읽는 법(비프로그래머용): 이번 v0.40.0은 search_provision·suggest_review_sources의 정규 응답에
답변 하단 표준 안내 완성형 standard_footer(법령 확인 + KISTEP 매뉴얼 원문 안내 2줄)를 부착합니다
— v0.29.0이 명시 이연했던 "검색·후보만 보고 답하는 경로" 갭 해소. 기존 whole-or-omit 규약이라
기존 결과·순서·절단은 byte 불변이며(예산 선반영 없음), 입력 스키마 무변(contract 0.30.0 →
재연결 불요)입니다. 동반 소항목으로 footer 값 선택 지시를 규정 도구 3종으로 확대하고 생략
폴백에 KISTEP 줄을 추가했습니다(텍스트 표면·pytest 잠금 담당).
Level A는 ①검색 무회귀(recall·도달) ②신규 footer 부착(검색·suggest) ③광역 suggest 지연
(내부 search 호출마다 footer 직렬화 검사 1회가 추가되는 미세 오버헤드 실측 — Codex 검토 반영)
④상세·매뉴얼 footer 무회귀를 봅니다. ★footer 검사는 전부 field_equals = WARN 축(러너 동결
규약 — 자동 BLOCK은 fetched_ok·returned_not_below 2종만·false-block-safe)이므로 이 spec의
차단력은 검색 무회귀에 한정되며, footer 자체의 결정론 잠금(부착 행렬·whole-or-omit·문자열
일치·suggest 오류 팽창 생략)은 pytest 신규 14건이 담당합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

# 규정 경로 footer 2줄(v0.30.0 문면·manual.py 상수 단일 출처와 글자 단위 일치 — pytest가 상수 잠금)
_FOOTER2 = (
    "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다.\n"
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(footer 부착의 검색 무영향)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN
            # 광역 응답은 16k 예산 경계에 닿으면 whole-or-omit으로 생략될 수 있음 — WARN 참고용
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN — 신규
        ],
    },
    {
        "name": "★신규 A — 협소 검색 응답 footer 글자 단위 일치(예산 여유 구간·결정적 부착)",
        "tool": "search_provision",
        # ★질의 표기 함정: "연구시설장비비"(붙여쓰기)는 규정 원문 표기("연구시설·장비비")와 달라
        # 토큰 AND 0건 — 가운뎃점 포함 원문 표기 사용(2026-08-06 LIVE 실측 returned=3)
        "args": {"query": "연구시설·장비비 통합관리"},
        "asserts": [
            {"kind": "returned_not_below", "value": 1},                                       # 회귀=BLOCK 후보
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN — 신규
        ],
    },
    {
        "name": "★신규 B — suggest 응답 footer + 광역 지연(내부 search 직렬화 오버헤드 실측)",
        "tool": "suggest_review_sources",
        "args": {"question": "연구개발비 이월과 연구시설장비비 통합관리 요건을 함께 검토해줘"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN — 신규
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 20.0},                                         # WARN — 광역 suggest
        ],
    },
    {
        "name": "무회귀 — 상세 응답 footer 불변(v0.29.0 승계·혁신법 제13조 JO)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN — 무회귀
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 무회귀
        ],
    },
    {
        "name": "무회귀 — 매뉴얼 도구 불변(b4-5 citation + 매뉴얼 4줄 footer — v0.39.0 승계·매뉴얼 footer 경로 무접촉)",
        "tool": "get_manual_section",
        "args": {"section_id": "b4-5"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「연구시설･장비비 통합관리제 운영･관리 매뉴얼」(26.7판) "
                      "Ⅴ. 통합 연구시설･장비비의 계상･지급･적립, 인쇄 p.14~17"},               # WARN
            {"kind": "field_equals", "path": "manual_meta.standard_footer",
             "value": _FOOTER2 + "\n"
                      "※ 매뉴얼 해설 부분은 「국가연구개발혁신법 매뉴얼」을 참고한 설명입니다. "
                      "매뉴얼은 법령·행정규칙이 아니며, 내용이 다를 때는 법령·행정규칙 원문이 우선합니다.\n"
                      "※ 인용 자료: 「연구시설･장비비 통합관리제 운영･관리 매뉴얼」"
                      "(국가연구개발혁신법 매뉴얼 별권 4) 26.7판(판번은 게시 세트 기준) · "
                      "법령 기준일 원문 미표기"},                                                # WARN — 무회귀
        ],
    },
]

LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 검색-only 경로 footer 발현(이번 릴리스의 존재 이유)",
        "probe_prompt": "국가연구개발 규정에서 '연구시설·장비비 통합관리'를 검색해서, 검색 결과에 잡히는 "
                        "조문들이 무엇인지 목록만 간단히 알려줘.",
        "expect_behavior": "호스트가 search_provision 결과만으로(상세 미조회) 답하는 경우에도 답변 하단에 "
                           "표준 안내 2줄(법령 확인 + KISTEP)이 글자 단위로 표시되는지 — 종전에는 이 경로에 "
                           "footer가 도달하지 않았음(v0.29.0 명시 이연 갭). 호스트가 상세를 조회해 버리면 "
                           "이 프로브는 관측 불가(N) — 검색 결과 목록 요청 문안이 상세 조회를 억제하는지 관찰.",
    },
    {
        "category": "★표적 — suggest 경로 footer 발현 + 선택 지시 확대 실효",
        "probe_prompt": "대학원생 인건비를 다른 과제로 옮겨 쓸 수 있는지 검토하려면 어떤 규정들을 어떤 "
                        "순서로 봐야 하는지 후보만 추천해줘.",
        "expect_behavior": "suggest_review_sources 후보 목록 기반 답변 하단에 표준 안내 2줄 발현. "
                           "매뉴얼 비인용 답변에서 footer 값 선택 지시가 도구 3종으로 확대된 효과가 "
                           "검색·후보 경로에서 처음 관측되는 축.",
    },
    {
        "category": "무회귀 — 상세 경로 footer 2줄 기존 거동 유지(검색+상세 혼합 대화 dedup)",
        "probe_prompt": "국가연구개발혁신법 제13조 원문을 확인해서 요지를 알려줘.",
        "expect_behavior": "get_provision_detail 기반 답변의 footer 2줄이 기존과 동일(중복 부착 0·답변당 1블록). "
                           "검색+상세를 모두 호출한 대화에서 동일 문자열 dedup('아무 하나만')이 유지되는지.",
    },
]
