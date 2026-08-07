"""v0.42.0 배포 전 LIVE acceptance spec — 「suggest fallback 요청 프레임 필터」.

읽는 법(비프로그래머용): suggest_review_sources에 keywords를 함께 넘기지 않으면 서버가 질문
표면에서 키워드를 규칙 추출합니다(fallback). 2026-08-07 재현에서 "…검토해야 할 규정 후보와
검토 순서"라는 질문의 **요청 형식어**가 그대로 검색어가 되어, 코퍼스 광역어 '검토'(258건)에
걸린 "규제의 재검토"류 무관 조문이 후보 상위를 점유했습니다. 이번 릴리스는 **질문 꼬리의
요청 절만** 잘라냅니다(끝에서 앞으로 훑다가 내용어를 만나면 중지). 같은 단어라도 조문 용어로
쓰이면 보존합니다 — "평가위원 후보 추천 기준"·"중장기 기술확보 목록"은 전건 유지.
어미 정규화는 도입하지 않습니다(명사 훼손·광역 어간 희석 회피).
응답 필드·shape·오류코드·입력 스키마 불변(contract 0.31.0 유지 → 재연결 불요).

Level A는 ①관측 결함 해소(extracted_keywords에서 프레임 노이즈 소멸·실질 명사 보존)
②법적 의미 보존('재검토 요청'류 질의에서 후보 무회귀) ③★프레임 명사가 조문 용어로 쓰인
질의의 후보 무회귀 ④검색 무회귀(search_provision 무접촉) ⑤빈 키워드 낙하 경로 정상
⑥footer/note 무회귀를 봅니다.
★extracted_keywords 검사는 field_equals = WARN 축(러너 동결 규약 — 자동 BLOCK은
fetched_ok·returned_not_below 2종만·false-block-safe)이므로 이 spec의 차단력은 recall 무회귀에
한정되며, 추출 규칙의 결정론 잠금은 pytest 신규 12건이 담당합니다.

★판정 주의(계획 §5-3): 잡음 제거의 정상 결과는 후보 수 **감소**입니다. total·returned의 감소
자체는 회귀가 아니며, 판정 기준은 "정답 조문 도달 + 오류 미증가 + 빈 결과 붕괴 없음"입니다.

★러너 규약상 한계(동결된 assert 5종을 그대로 쓰기 위한 제약):
  - returned_not_below는 응답의 `results` 키(= search_provision 전용)를 세므로 suggest 응답
    (`candidates` 키)에는 쓸 수 없습니다. 잘못 쓰면 항상 0으로 읽혀 false BLOCK이 납니다.
    따라서 suggest 체크의 후보 수는 field_equals(path="returned") = WARN 관측으로만 봅니다.
  - suggest의 fetched_ok는 "그 규정이 errors에 없다"만 보므로 후보 존재까지 보증하지 않습니다.
  - 결과적으로 이 spec의 자동 차단력은 search_provision 무회귀 체크에 집중되며, fallback 추출
    규칙의 결정론 잠금은 pytest 신규 12건이, 후보 품질 판정은 Level B 수동 eval이 담당합니다.

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

# v0.41.0 인접 지시 문면(main._STD_FOOTER_NOTE 단일 출처 — pytest가 상수 잠금·이번 릴리스 무접촉)
_NOTE = (
    "아래 standard_footer 값은 검색 결과·후보 목록만 나열하는 답변(결과 0건 포함)에도 "
    "최종 답변의 마지막 줄들로 그대로 1회 표시하십시오. 매뉴얼 내용을 인용한 답변은 "
    "매뉴얼 응답의 standard_footer를 대신 사용하고, 같은 취지 안내를 중복 부착하지 마십시오."
)

# 관측 결함 질문(2026-08-07 결정론 재현) — 구: 8키워드 중 5개가 요청 형식어
_A1_QUESTION = "연구개발비를 다른 비목으로 전용할 때 검토해야 할 규정 후보와 검토 순서"

CHECKS = [
    {
        "name": "★표적 A — 관측 질문의 fallback 키워드에서 요청 형식어 소멸(실질 명사 3개 보존)",
        "tool": "suggest_review_sources",
        "args": {"question": _A1_QUESTION},
        "asserts": [
            # 구 baseline: ['연구개발비','비목','전용할','검토해야','규정','후보','검토','순서']
            {"kind": "field_equals", "path": "extracted_keywords",
             "value": ["연구개발비", "비목", "전용할"]},                                    # WARN — 이번 릴리스 표적
            {"kind": "field_equals", "path": "keyword_source", "value": "fallback"},      # WARN
            # ★정답 도달: '연구개발비'·'비목'이 살아 있으므로 후보가 비지 않아야 함.
            #   구 baseline total=77은 '검토' 노이즈 포함치라 비교 대상이 아님(계획 §5-3).
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "field_equals", "path": "returned", "value": 15},                    # WARN — cap 도달 관측
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            # 키워드 8→3으로 fan-out 호출이 줄어 지연도 감소 방향
            {"kind": "latency_under", "value": 20.0},                                     # WARN
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},       # WARN — v0.40.0 무회귀
            {"kind": "field_equals", "path": "standard_footer_note", "value": _NOTE},     # WARN — v0.41.0 무회귀
        ],
    },
    {
        "name": "★표적 B — 법적 의미 보존('재검토 요청 절차'는 무접촉·정답 조문 도달)",
        "tool": "suggest_review_sources",
        "args": {"question": "제재처분에 대한 재검토 요청 절차를 알려달라"},
        "asserts": [
            # '재검토'는 어간이 달라 프레임 규칙 미해당·'요청'·'절차'는 stopword 아님 → 구 동작과 동일
            {"kind": "field_equals", "path": "extracted_keywords",
             "value": ["제재처분에", "재검토", "요청", "절차"]},                            # WARN — 무회귀
            {"kind": "fetched_ok", "rule_set_id": "innovation_act"},                      # 회귀=BLOCK 후보
            {"kind": "field_equals", "path": "returned", "value": 15},                    # WARN — cap 도달 관측
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
        ],
    },
    {
        "name": "★신규 B2 — 프레임 명사가 조문 용어인 질의는 무접촉(적대검토 MAJOR-1 반례)",
        "tool": "suggest_review_sources",
        "args": {"question": "평가위원 후보 추천 기준을 알려줘"},
        "asserts": [
            # 뒤에 내용어('기준')가 있으므로 꼬리 요청 절이 아니다 → 전건 보존
            {"kind": "field_equals", "path": "extracted_keywords",
             "value": ["평가위원", "후보", "추천", "기준"]},                                # WARN — 보존 잠금
            {"kind": "field_equals", "path": "keyword_source", "value": "fallback"},      # WARN
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
        ],
    },
    {
        "name": "★신규 C — 요청 형식만 있는 질문은 빈 키워드로 degraded 낙하(fan-out 미시작)",
        "tool": "suggest_review_sources",
        "args": {"question": "검토 순서와 규정 후보 목록 추천"},
        "asserts": [
            {"kind": "field_equals", "path": "extracted_keywords", "value": []},          # WARN — 설계된 낙하
            {"kind": "field_equals", "path": "keyword_source", "value": "fallback"},      # WARN
            {"kind": "field_equals", "path": "total", "value": 0},                        # WARN
            # 오류 envelope이 아닌 정규 반환 — footer/note 동반(v0.40.0·v0.41.0 커버리지 무회귀)
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},       # WARN
            {"kind": "field_equals", "path": "standard_footer_note", "value": _NOTE},     # WARN
            {"kind": "latency_under", "value": 5.0},                                      # WARN — 검색 미수행
        ],
    },
    {
        "name": "무회귀 — client 제공 keywords는 프레임 필터 무접촉(호스트 의도 보존)",
        "tool": "suggest_review_sources",
        "args": {"question": "비목 전용 검토", "keywords": ["검토", "규정", "연구개발비"]},
        "asserts": [
            # 프레임 필터는 fallback 전용 — client 배열은 글자 단위 그대로
            {"kind": "field_equals", "path": "extracted_keywords",
             "value": ["검토", "규정", "연구개발비"]},                                      # WARN — 무접촉 잠금
            {"kind": "field_equals", "path": "keyword_source", "value": "client"},        # WARN
            {"kind": "field_equals", "path": "returned", "value": 15},                    # WARN — cap 도달 관측
        ],
    },
    {
        "name": "무회귀 핵심 — search_provision 무접촉(대형 규정 도달 + recall)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "latency_under", "value": 16.0},                                     # WARN
        ],
    },
    {
        "name": "무회귀 — 상세 응답 불변(혁신법 제13조 JO·footer 유지·note 미부착)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "standard_footer", "value": _FOOTER2},       # WARN
            {"kind": "field_equals", "path": "standard_footer_note", "value": "<missing>"},  # WARN
        ],
    },
]

LEVEL_B_PROMPTS = [
    {
        "category": "★표적 P1 — 후보 추천 품질(관측 결함 재현 문안·keywords 생략 유도)",
        "probe_prompt": "연구개발비를 다른 비목으로 전용할 때 검토해야 할 규정 후보와 검토 순서를 "
                        "규정 도구가 추천한 결과 그대로 알려줘. 개별 조문 본문은 조회하지 마.",
        "expect_behavior": "후보 목록에 '규제의 재검토'·'제재처분의 절차 및 재검토 요청 등'처럼 "
                           "비목 전용과 무관한 조문이 상위에 오지 않아야 PASS. ★반드시 응답의 "
                           "keyword_source를 함께 확인할 것 — 'client'이면 호스트가 키워드를 직접 "
                           "제공한 것이므로 이번 릴리스(fallback 개선)의 효과는 '관측 불가'로 "
                           "기록하고 PASS로 포장하지 말 것(계획 §1-3 한계 고지).",
    },
    {
        "category": "★표적 P2 — 법적 의미 보존 음성 대조('검토'가 실질어인 질의)",
        "probe_prompt": "제재처분을 받은 기관이 재검토를 요청하는 절차와, 연구개발기관에 대한 "
                        "사전 검토 규정을 함께 확인해줘.",
        "expect_behavior": "'재검토 요청' 절차 조문과 '사전 검토' 조문이 모두 근거로 제시되어야 "
                           "PASS. 프레임 필터가 실질 조문어 '검토'까지 지웠다면 두 조문 중 하나가 "
                           "누락되거나 답변이 일반 지식으로 후퇴함(BLOCK 신호).",
    },
    {
        "category": "무회귀 P3 — 하단 표준 안내 발현 유지(v0.41.0 성과 보존)",
        "probe_prompt": "국가연구개발 규정에서 정확히 '연구시설·장비비 통합관리'라는 문구로 검색해. "
                        "검색 결과에 나온 조문 번호와 조문명만 간단히 목록으로 정리해줘. "
                        "각 조문의 본문을 열거나 내용·요지를 추가로 확인하지 마.",
        "expect_behavior": "v0.41.0에서 PASS한 문안. 목록형 답변 하단에 footer 2줄이 글자 단위로 "
                           "유지되는지 — 이번 릴리스가 footer 경로를 건드리지 않았음의 확인.",
    },
    {
        "category": "무회귀 P4 — 요청 형식만 있는 질문의 안내 낙하",
        "probe_prompt": "검토 순서와 규정 후보 목록을 추천해줘.",
        "expect_behavior": "검토 대상이 무엇인지 없는 질문이므로, 서버가 무관 조문을 나열하는 대신 "
                           "AI가 어떤 사안인지 되묻거나 키워드를 보강해 재조회하면 PASS. 엉뚱한 "
                           "조문을 근거처럼 제시하면 FAIL.",
    },
]
