"""v0.36.0 배포 전 LIVE acceptance spec — 「배포 후 관측 반영 정비: 도구 read-only 주석 + 혁신법 시행령 fallback 현행화」.

읽는 법(비프로그래머용): 이번 v0.36.0은 ①도구 7종에 MCP 표준 tool annotations(readOnlyHint 등)를
부여하고(메타데이터-only·도구 로직·응답 문면 무변) ②혁신법 시행령 fallback MST를 현행
288335(2026-07-28 시행)로 갱신합니다(입력 스키마 무변·contract 0.26.0 유지 → 웹 커넥터 재연결
불요). Level A(자동)는 규정·매뉴얼 트랙 무회귀와 신 MST 정합(개정 안내 소멸·신설 조문 조회)을
결정론으로 확인합니다.

★annotations는 도구 응답이 아니라 tools/list 메타데이터라 본 러너(assert 5종 동결)가 검증하지
않습니다 — 검증 표면은 ⓐpytest tests/test_annotations.py 15건(registry·wire 양면) ⓑ배포 시
터널 스모크의 tools/list JSON에 readOnlyHint 존재 확인 ⓒLevel B(ChatGPT 도구 상세의 '쓰기'
배지 소멸)입니다.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 차단 안 함]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

_LAW_LINE = "※ 정확한 최종 확인은 국가법령정보센터(law.go.kr)의 관련 규정 원문을 기준으로 해주시기 바랍니다."
_MANUAL_SOURCE_LINE = (
    "※ 「국가연구개발혁신법 매뉴얼」 등 연구행정 관련 매뉴얼 원문은 "
    "KISTEP 홈페이지(www.kistep.re.kr)에서 확인하시기 바랍니다."
)
_PROVISION_FOOTER = _LAW_LINE + "\n" + _MANUAL_SOURCE_LINE

# 신설 제35조의2 실측 verbatim(2026-08-05 LIVE 확보·242자) — 빈 본문 회귀 차단(diff 적대검토 MINOR 반영)
_JO003502_TITLE = "연구개발성과의 교부ㆍ열람을 위한 기탁"
_JO003502_CONTENT = (
    "제35조의2(연구개발성과의 교부ㆍ열람을 위한 기탁)\n"
    "① 법 제17조제3항에서 \"대통령령으로 정하는 연구개발성과\"란 제3조제3호에 따른 논문을 말한다.\n"
    "② 연구개발기관과 연구자가 법 제17조제3항에 따라 연구개발성과를 기탁하려는 경우에는 전담기관이 "
    "별도로 정하는 방법과 절차에 따라야 한다.\n"
    "③ 중앙행정기관의 장은 연구개발기관과 연구자가 제2항에 따른 기탁의 방법 및 절차를 알 수 있도록 "
    "해당 기관의 인터넷 홈페이지에 게시해야 한다."
)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 대형 규정 도달 + recall(annotations·manifest 갱신의 검색 무영향)",
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
        "name": "★신규 A — 시행령 doc-level(law:288335): fallback 정합 신호(개정 안내 소멸·시행일·조문 수 69)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288335"},
        "asserts": [
            {"kind": "field_equals", "path": "effective_date", "value": "2026-07-28"},        # WARN — 신규
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},        # WARN — manifest=LIVE 정합 직접 신호
            {"kind": "field_equals", "path": "articles_count", "value": 69},                  # WARN — 68→69(제35조의2 신설)
        ],
    },
    {
        "name": "★신규 B — 신설 제35조의2(가지조문 JO003502) 신 MST 상세: 제목·본문 242자 verbatim 정합",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288335:JO003502"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 신규
            {"kind": "field_equals", "path": "title", "value": _JO003502_TITLE},               # WARN — 빈 응답 회귀 차단
            {"kind": "field_equals", "path": "content", "value": _JO003502_CONTENT},           # WARN — 본문 verbatim 정합
        ],
    },
    {
        "name": "무회귀 — 규정 상세 footer 2줄(구 MST 무관 혁신법 본법 경로 불변)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283849:JO0013"},
        "asserts": [
            {"kind": "field_equals", "path": "standard_footer", "value": _PROVISION_FOOTER},  # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "무회귀 — 매뉴얼 트랙 완전 무변(별권 1 b1-3-6 citation 글자 단위 불변)",
        "tool": "get_manual_section",
        "args": {"section_id": "b1-3-6"},
        "asserts": [
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
            {"kind": "field_equals", "path": "citation",
             "value": "「학생인건비통합관리 제도 매뉴얼」(26.7판) 제3장 6. 학생인건비 이자 처리, 인쇄 p.32"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). ★v0.36.0 = annotations의 호스트 표면 효과(ChatGPT
# '쓰기' 배지·확인 다이얼로그)와 갱신 manifest의 무회귀가 관측 표적. annotations는 클라이언트가
# 도구 목록을 갱신해야 반영되므로, ChatGPT는 커넥터 재스캔(또는 재등록) 후 관찰할 것.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — ChatGPT 도구 분류(UI 관찰·재스캔 후): '쓰기' 배지 소멸 + 확인 다이얼로그 마찰 감소",
        "probe_prompt": "(UI 관찰) ChatGPT 개발자 모드 커넥터 재스캔 후 도구 상세에서 분류 배지를 확인하고, "
                        "이어서 '국가연구개발혁신법 제13조 내용 알려줘' 등 조회 1건을 실행.",
        "expect_behavior": "종전 실측(2026-08-02): readOnlyHint 부재로 빨간 '쓰기' 배지 + 확인 다이얼로그(5시험 중 "
                           "2회). 기대: 도구가 읽기 전용으로 분류되고 확인 마찰이 줄었는지. InstructionAttempt 경고는 "
                           "이번 변경(description 무변)과 무관하게 잔존할 수 있음 — 잔존해도 실패 아님(별도 backlog).",
    },
    {
        "category": "★표적 — 혁신법 시행령 신설 조문(제35조의2) 라이브 도달",
        "probe_prompt": "국가연구개발혁신법 시행령에서 연구개발성과의 교부·열람을 위한 기탁 절차가 어떻게 "
                        "규정되어 있는지 조문 근거와 함께 알려줘.",
        "expect_behavior": "search_provision 또는 시행령 doc-level 경유로 제35조의2(2026-07-28 신설) 도달 — "
                           "신 MST 288335 기준 조문이 verbatim 인용되고 구판(68조문) 기준 '해당 조문 없음' 류 "
                           "오답이 없는지. footer 2줄 표시 여부 관찰.",
    },
    {
        "category": "무회귀 — 매뉴얼 트랙(별권 1) footer 4줄·citation 표시 유지",
        "probe_prompt": "학생인건비통합관리 제도 매뉴얼에서 통합관리계정 이자 처리를 어떻게 안내하는지 알려줘.",
        "expect_behavior": "b1-3-6 도달·citation(인쇄 p.32)·footer 4줄 표시가 v0.35.0 eval과 동일하게 유지되는지 "
                           "(annotations 추가가 Claude 호스트 표시 거동에 회귀를 만들지 않는지 확인용).",
    },
]
