"""v0.41.0 배포 전 LIVE acceptance spec — 「검색·후보 footer 발화 신호 보강」.

읽는 법(비프로그래머용): v0.40.0 배포 후 라이브 eval에서 검색-only(P1)·후보 나열형(P3) 답변에
하단 표준 안내가 표시되지 않는 사례가 나왔고, 배포 전 진단 프로브(P0·2026-08-06)로 서버는 정상
부착 중임을 확정했습니다(호스트가 footer 값을 글자 단위로 재현 — 실패 지점은 답변 조립 시점의
지시 미발화). 이번 릴리스는 search·suggest 정규 응답에 인접 지시 standard_footer_note를
standard_footer 바로 앞 키로 additive 부착하고(footer-먼저 2단 폴백 — v0.40.0 부착 커버리지
무회귀), 서버 지시문 예외 문면을 정밀화합니다. 입력 스키마 무변(contract 0.31.0 → 재연결 불요).
Level A는 ①검색 무회귀(recall·도달) ②note+footer 동반 부착 ③광역 suggest 지연(직렬화 검사
최대 2회로 증가한 미세 오버헤드) ④상세·매뉴얼 무회귀(상세에는 note 미부착)를 봅니다.
★footer·note 검사는 전부 field_equals = WARN 축(러너 동결 규약 — 자동 BLOCK은
fetched_ok·returned_not_below 2종만·false-block-safe)이므로 이 spec의 차단력은 검색 무회귀에
한정되며, note 결정론 잠금(부착 행렬·키 순서·2단 폴백·상세 미부착·문면)은 pytest 신규 8건이
담당합니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

# 규정 경로 footer 2줄(v0.30.0 문면 승계·manual.py 상수 단일 출처와 글자 단위 일치 — pytest가 상수 잠금)
_FOOTER2 = (
    "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다.\n"
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)

# v0.41.0 인접 지시 문면(main._STD_FOOTER_NOTE 단일 출처 — pytest가 상수 잠금)
_NOTE = (
    "아래 standard_footer 값은 검색 결과·후보 목록만 나열하는 답변(결과 0건 포함)에도 "
    "최종 답변의 마지막 줄들로 그대로 1회 표시하십시오. 매뉴얼 내용을 인용한 답변은 "
    "매뉴얼 응답의 standard_footer를 대신 사용하고, 같은 취지 안내를 중복 부착하지 마십시오."
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(note 추가의 검색 무영향)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},
            {"kind": "returned_not_below", "value": 10},                                      # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 16.0},                                         # WARN
            # 광역 응답은 16k 경계에서 2단 폴백(note 생략→footer 유지) 또는 전체 생략 가능 — WARN 참고
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN
        ],
    },
    {
        "name": "★신규 A — 협소 검색 응답 note+footer 동반 부착(예산 여유 구간·결정적)",
        "tool": "search_provision",
        # ★질의 표기 함정(v0.40.0 승계): "연구시설장비비"(붙여쓰기)는 원문 표기("연구시설·장비비")와
        # 달라 토큰 AND 0건 — 가운뎃점 포함 원문 표기 사용(2026-08-06 LIVE 실측 returned=3)
        "args": {"query": "연구시설·장비비 통합관리"},
        "asserts": [
            {"kind": "returned_not_below", "value": 1},                                       # 회귀=BLOCK 후보
            {"kind": "field_equals", "path": "standard_footer_note", "value": _NOTE},         # WARN — 신규
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN
        ],
    },
    {
        "name": "★신규 B — suggest 응답 note+footer + 예산 직전 구간 부착 유지(P0 실측 13.6k~15.8k 대역)",
        "tool": "suggest_review_sources",
        # P0 프로브에서 ChatGPT가 실제 전달했던 question 문자열(2026-08-06) — 재현 14,588자·부착 확인.
        # note 추가 후에도 부착이 유지되는지(2단 폴백 미발동 구간) LIVE로 재확인.
        "args": {"question": "연구개발비를 다른 비목으로 전용할 때 검토해야 할 규정 후보와 검토 순서를 "
                             "추천해 달라는 요청. 개별 조문 본문은 조회하지 않고, 규정 도구가 반환한 추천 "
                             "결과를 그대로 제시한다."},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer_note", "value": _NOTE},         # WARN — 신규
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN
            {"kind": "absent_error_code", "value": "timeout"},                                # WARN
            {"kind": "latency_under", "value": 20.0},                                         # WARN — 광역 suggest
        ],
    },
    {
        "name": "무회귀 — 상세 응답 footer 불변 + note 미부착(기확인 정상 경로 무접촉·혁신법 제13조 JO)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},           # WARN — 무회귀
            {"kind": "field_equals", "path": "standard_footer_note", "value": "<missing>"},   # WARN — 상세 무접촉
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 매뉴얼 도구 불변(b4-5 citation + 매뉴얼 4줄 footer — 매뉴얼 경로 무접촉)",
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
        "category": "★표적 P1′ — 검색-only 목록형 footer 발현(v0.40.0 P1과 동일 문안 A/B)",
        "probe_prompt": "국가연구개발 규정에서 정확히 '연구시설·장비비 통합관리'라는 문구로 검색해. "
                        "검색 결과에 나온 조문 번호와 조문명만 간단히 목록으로 정리해줘. "
                        "각 조문의 본문을 열거나 내용·요지를 추가로 확인하지 마.",
        "expect_behavior": "v0.40.0 eval에서 FAIL했던 바로 그 문안. 인접 지시 note가 데이터와 함께 "
                           "소비되면서 목록만 나열하는 답변 하단에도 footer 2줄이 글자 단위로 표시되는지 "
                           "— 이번 릴리스의 존재 이유. note 문면 자체가 답변에 옮겨지면 안 됨(별도 관측).",
    },
    {
        "category": "★표적 P2′ — suggest 후보 나열형 footer 발현(v0.40.0 P3 재시도와 동일 취지 문안·ChatGPT)",
        "probe_prompt": "korean-rnd-regs-mcp 규정 도구로 확인해줘. 연구개발비를 다른 비목으로 전용할 때 "
                        "검토해야 할 규정 후보와 검토 순서를 도구가 추천한 결과 그대로 알려줘. "
                        "개별 조문 본문은 조회하지 마.",
        "expect_behavior": "후보 나열형 답변 하단 footer 2줄 발현. ChatGPT는 P0에서 마지막 필드 소실을 "
                           "보고했으므로, footer 직전에 배치된 note가 도달해 폴백(직접 표시)이라도 "
                           "발화하는지 관찰. 미발현 시 마지막 필드 소실 대역폭이 note까지인지 후속 키 "
                           "나열 프로브로 확인.",
    },
    {
        "category": "무회귀 P3′ — 매뉴얼+규정 혼합에서 매뉴얼 footer 단독 선택 유지(v0.40.0 P2 동일 문안)",
        "probe_prompt": "학생인건비 통합관리기관에서 학생인건비를 사용할 수 있는 용도와 그 근거 규정을 "
                        "매뉴얼 해설과 함께 알려줘.",
        "expect_behavior": "매뉴얼 인용 답변은 매뉴얼 footer(4줄)를 우선 선택하고 규정 2줄을 덧붙이지 "
                           "않는 기존 정상 동작(P2 확인) 유지 — note 신설이 중복 부착을 유발하지 않는지. "
                           "note 문면에 매뉴얼 우선·중복 금지가 내장되어 있음.",
    },
    {
        "category": "음성 대조 P4′ — 서버 운영 안내 답변에는 footer 미부착(예외 보존)",
        "probe_prompt": "이 MCP 서버가 지금 정상 연결되어 있는지 상태만 확인해줘.",
        "expect_behavior": "health 등 도구 상태 확인 답변에는 하단 표준 안내가 붙지 않아야 PASS — "
                           "예외 문면 정밀화가 운영 안내 예외(원래 취지)를 보존했는지의 음성 대조.",
    },
]
