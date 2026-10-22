"""v0.58.0 배포 전 LIVE acceptance spec — 사용자에게 보이는 규정 안내문 정비.

읽는 법(비프로그래머용): 이번 릴리스는 응답 문구의 값만 바꿉니다(실행 로직·응답 필드·규정 데이터 무변경·
contract 0.36.0 유지·재연결 불요).
  ①known_limitations(검색 매치·후보·상세의 warnings) 62규정에서 개발 용어·변동값 제거 — 규정별 길이 비증가
  ②중기법 제27조의3 시행일 문장(부칙 제1조·2026-05-26·effective_date 의미)
  ③revision_notice "manifest 기준 ID" → "등록 기준 ID", "(manifest 시행일 갱신 권장)" 삭제

returned_not_below 값은 v0.57.0 코드로 같은 날(2026-10-22) 측정한 값이다. 문면이 짧아지면 같은 예산에 매치가
더 실릴 수는 있어도 줄어들 수는 없다(검색 절단 = 앞에서부터 누적). 줄면 데이터 변동인지 provision_id 집합으로
먼저 가린다(2026-10-22 같은 세션 A/B: 10질의 전부 기존 목록이 새 목록의 접두사·returned +0~+1·suggest 후보 동일·66문서 content_format 변화 0).

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out(릴리스 간 동일 문안)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 17},                                  # 회귀=BLOCK 후보 — v0.57.0 코드 2026-10-22 실측값
            {"kind": "absent_error_code", "value": "auth_failed"},                        # WARN — 정상 키 오탐 감시
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "★표적 — 절단 질의 '기술료' returned 비감소(문면 단축 = 같은 예산에 매치 유지 또는 추가)",
        "tool": "search_provision",
        "args": {"query": "기술료"},
        "asserts": [
            {"kind": "returned_not_below", "value": 16},                                  # 회귀=BLOCK 후보 — v0.57.0 실측값
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "★표적 — 절단 질의 '연구보안' returned 비감소(문면 단축 = 같은 예산에 매치 유지 또는 추가)",
        "tool": "search_provision",
        "args": {"query": "연구보안"},
        "asserts": [
            {"kind": "returned_not_below", "value": 12},                                  # 회귀=BLOCK 후보 — v0.57.0 실측값
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "★표적 — 절단 질의 '협약 변경' returned 비감소(문면 단축 = 같은 예산에 매치 유지 또는 추가)",
        "tool": "search_provision",
        "args": {"query": "협약 변경"},
        "asserts": [
            {"kind": "returned_not_below", "value": 11},                                  # 회귀=BLOCK 후보 — v0.57.0 실측값
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "★표적 — 절단 질의 '제재부가금' returned 비감소(문면 단축 = 같은 예산에 매치 유지 또는 추가)",
        "tool": "search_provision",
        "args": {"query": "제재부가금"},
        "asserts": [
            {"kind": "returned_not_below", "value": 14},                                  # 회귀=BLOCK 후보 — v0.57.0 실측값
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "★표적 — 절단 질의 '연구노트' returned 비감소(문면 단축 = 같은 예산에 매치 유지 또는 추가)",
        "tool": "search_provision",
        "args": {"query": "연구노트"},
        "asserts": [
            {"kind": "returned_not_below", "value": 18},                                  # 회귀=BLOCK 후보 — v0.57.0 실측값
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "★표적 — 절단 질의 '학생인건비' returned 비감소(문면 단축 = 같은 예산에 매치 유지 또는 추가)",
        "tool": "search_provision",
        "args": {"query": "학생인건비"},
        "asserts": [
            {"kind": "returned_not_below", "value": 12},                                  # 회귀=BLOCK 후보 — v0.57.0 실측값
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "★표적 — 절단 질의 '연구시설 장비' returned 비감소(문면 단축 = 같은 예산에 매치 유지 또는 추가)",
        "tool": "search_provision",
        "args": {"query": "연구시설 장비"},
        "asserts": [
            {"kind": "returned_not_below", "value": 14},                                  # 회귀=BLOCK 후보 — v0.57.0 실측값
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
        ],
    },
    {
        "name": "★표적 — 개정 반영 안내 새 문구(혁신법 시행령 288773 의도적 유지 = 상시 표시)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773"},
        "asserts": [
            {"kind": "field_equals", "path": "revision_notice",
             "value": "개정 반영: 시행일 2026-09-11 (등록 기준 ID 288773 → 최신 ID 288335)"},   # WARN — 'manifest' 미노출
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
        ],
    },
    {
        "name": "★표적 — 중기법 제27조의3 상세 warnings에 조문 시행일 문장(eflaw 정상 경로 = stage_notice 미부착)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987:JO002703"},
        "asserts": [
            {"kind": "field_equals", "path": "warnings.0", "value": "제27조의3(사업화 금융지원)은 법률 제21704호 부칙 제1조(공포한 날부터 시행)에 따라 2026-05-26부터 시행되었습니다. effective_date는 법령 판본의 시행일입니다. 종전 제27조의3은 제27조의4로 이동."},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "★표적 — 검색 경로 중기법 제27조의3 1위 유지 + 같은 문장",
        "tool": "search_provision",
        "args": {"query": "사업화 금융지원"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "sme_tech_act"},                        # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 5},                                  # 회귀=BLOCK 후보
            {"kind": "field_equals", "path": "results.0.provision_id", "value": "law:281987:JO002703"},  # WARN — v0.57.0 실측 1위
            {"kind": "field_equals", "path": "results.0.warnings.0", "value": "제27조의3(사업화 금융지원)은 법률 제21704호 부칙 제1조(공포한 날부터 시행)에 따라 2026-05-26부터 시행되었습니다. effective_date는 법령 판본의 시행일입니다. 종전 제27조의3은 제27조의4로 이동."},  # WARN
        ],
    },
    {
        "name": "무회귀 — suggest 경로(후보 warnings 공유) 정상",
        "tool": "suggest_review_sources",
        "args": {"question": "연구책임자를 변경하려고 하는데 어떤 규정을 봐야 하나요?", "keywords": ["연구책임자", "변경"]},
        "asserts": [
            {"kind": "absent_error_code", "value": "auth_failed"},                        # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "latency_under", "value": 30.0},                                     # WARN — 기록용
        ],
    },
]

LEVEL_B_PROMPTS = [
    {
        "category": "재현 게이트 D — 제27조의3 조문 시행일(v0.57.0 문안 verbatim·검색 경로)",
        "probe_prompt": "중소기업 기술혁신 촉진법 제27조의3은 언제부터 시행된 조문인지 도구로 확인해서 알려줘.",
        "expect_behavior": "2026-05-26(법률 제21704호 부칙 제1조 '공포한 날부터')을 도구 응답 근거로 답하고 법령 판본 "
                           "시행일과 구분. 판본 날짜를 조문 시행일로 단정하거나 보도 기준 '6월경'으로 답하면 실패. "
                           "웹 사용 여부는 보조 지표(Claude 3회).",
    },
    {
        "category": "재현 게이트 D' — 제27조의3 조문 상세 경로 분리",
        "probe_prompt": "중소기업 기술혁신 촉진법 제27조의3 조문을 get_provision_detail로 원문 조회해서, 이 조문이 "
                        "언제부터 시행됐는지 근거와 함께 알려줘.",
        "expect_behavior": "상세 warnings의 부칙 근거 문장을 반영해 2026-05-26으로 답함. effective_date(법령 판본 "
                           "시행일)를 조문 시행일로 쓰면 실패.",
    },
    {
        "category": "하단 안내 — 지시문(standard_footer_note) 생략 질의의 footer 표시(v0.58.0 부수 효과 관측)",
        "probe_prompt": "국가연구개발사업의 연구보안 관련 규정을 search_provision으로 검색해서 어떤 조문들이 있는지 목록으로 정리해줘.",
        "expect_behavior": "답변 마지막에 도구 응답의 standard_footer 2줄(법령 원문 확인·매뉴얼 원문 안내)을 그대로 표시. "
                           "응답에 footer만 있고 note가 없는 질의다(2026-10-22 실측). 3회 중 2회 이상 미표시면 "
                           "'검색 footer·note 예산 예약' 별도 릴리스 근거로 기록.",
    },
    {
        "category": "안내문 UX — 서식·별지 안내에 내부 용어 미노출",
        "probe_prompt": "산업기술혁신사업 공통 운영요령에 있는 서식들의 내용을 도구로 확인할 수 있는지 알려줘.",
        "expect_behavior": "서식은 도구로 조회할 수 없어 공식 원문에서 확인해야 한다고 안내. schema·BP·manifest 같은 "
                           "내부 용어가 답변에 나오면 실패.",
    },
]
