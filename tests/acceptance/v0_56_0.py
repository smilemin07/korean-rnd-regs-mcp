"""v0.56.0 배포 전 LIVE acceptance spec — 시행 도래 반영(manifest 현행화와 제목 변경 규정 회복).

읽는 법(비프로그래머용): 이번 릴리스는 데이터·문면만 바꿉니다(실행 로직 무변경·contract 0.36.0 유지·
재연결 불요).
  ①manifest 6건 현행화(2026-10-14 재감사·검색 행 기준): innovation_act 283413→290757 ·
    industry_tech_act 280041→284363 · sme_tech_decree 287505→289953 · defense_tech_act 258057→283941 ·
    facility_equipment_standard 2100000278230→2100000285744 · ★msit_rnd_processing 2100000228284→2100000285280
  ②★msit_rnd_processing 정식 제목 변경 반영 — 2026-10-14 재감사에서 2023-08-24 구판 서빙을 확인. 원인 =
    2026-09-18 개정(훈령 제325호)으로 제목에서 '소관'이 빠져 제목 정확일치 resolve가 0행(이번 릴리스의 핵심).
  ③stage_notice 정리: innovation_act 제거(합본 = 시행 본문) · industry_tech_act 284363 재결박 ·
    innovation_decree는 manifest 288773 의도적 유지 + 이미 시행된 09-11 절 삭제.

★v0.55.0 spec이 예고한 반전(그 spec의 D·E 체크): 2026-09-11부터 혁신법 시행령 현행 판본이 288335로
바뀌어 조문 수가 71이 되고 제35조의2가 조회된다 — 아래 체크가 그 반전된 기준값이다.

★구 ID(law:283413 · admrul:2100000228284 등)가 not_found인 것은 회귀가 아니라 정상입니다(manifest 갱신으로
구 ID 직접 경로 차단 — not_found 문면이 search_provision 재검색으로 현행 ID 회복을 안내, v0.50.0~).

resolve 캐시(86,400s) 오염 회피: 러너는 새 프로세스(fresh client)로 실행(run.py 1회 구동 기본 충족).

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]

정직 선언(러너 한계): 폴백 경로(검색 실패·eflaw 실패)의 고지 문면은 이 러너로 재현할 수 없다(라이브 상위
API를 고장 낼 수 없음). 그 경로는 pytest 가드(test_stage_eflaw.py·test_tools.py stage_notice 가드)가 맡는다.
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out 대형 규정 도달 + recall(릴리스 간 동일 문안)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — 대량이면 infra 여부 사람 판정
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "★표적 A — msit 신판 문서레벨(2100000285280·resolve 성공 = 폴백 고지·개정 반영 안내 미발화)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000285280"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 신 ID 실도달
            {"kind": "field_equals", "path": "effective_date", "value": "2026-09-18"},    # WARN — ★신판 식별
            {"kind": "field_equals", "path": "resolve_fallback_notice", "value": "<missing>"},  # WARN — ★발화 = 제목 불일치 재발
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN — manifest = 현행
            {"kind": "field_equals", "path": "articles_count", "value": 29},              # WARN — 사전 실측(제6조 삭제·제17조의2 신설)
            {"kind": "field_equals", "path": "annexes_count", "value": 8},                # WARN — 별표 1·별지 5·별첨 2
        ],
    },
    {
        "name": "★표적 B — msit 신설 제17조의2(특수관계인 참여 관리) 도달 = 구판 서빙 해소의 내용 증거",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000285280:JO001702"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 구판(2023)에는 없는 조문
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "★표적 C — msit 검색 fan-out 경로 도달(신설 조문 핵심어)",
        "tool": "search_provision",
        "args": {"query": "특수관계인"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "msit_rnd_processing"},                 # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "field_equals", "path": "results.0.provision_id",
             "value": "admrul:2100000285280:JO001702"},                                    # WARN — 사전 실측(2026-10-15) 1위 = 제17조의2(최종 결과 도달·Redteam 보강)
        ],
    },
    {
        "name": "회복 — 구 msit ID는 not_found(재검색 안내 문면으로 현행 ID 회복)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000228284"},
        "asserts": [
            {"kind": "field_equals", "path": "errors.0.code", "value": "not_found"},      # WARN — 정상(위 docstring)
            {"kind": "field_equals", "path": "errors.0.message", "value": (               # WARN — 재검색 회복 안내 문면(v0.50.0 §5.41)
                "지원 규정 목록에 admrul:2100000228284 항목 없음 — 규정 개정으로 문서 ID가 바뀐 구 ID이거나 미지원 규정일 수 "
                "있으니, 질문 핵심 용어로 search_provision을 재호출해 현행 provision_id를 확인하십시오")},
        ],
    },
    {
        "name": "회복 — 구 혁신법 ID는 not_found(v0.51.0 선례와 동일 성질)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283413"},
        "asserts": [
            {"kind": "field_equals", "path": "errors.0.code", "value": "not_found"},      # WARN — 정상
        ],
    },
    {
        "name": "표적 — innovation_act 신 manifest 290757 문서레벨(고지 제거 = warnings 빈 배열)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:290757"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 42},              # WARN — 사전 실측(2026-10-14)
            {"kind": "field_equals", "path": "effective_date", "value": "2026-10-02"},    # WARN — ★신판 식별
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN — manifest = 현행
            {"kind": "field_equals", "path": "resolve_fallback_notice", "value": "<missing>"},  # WARN
            {"kind": "field_equals", "path": "warnings.0", "value": "<missing>"},         # WARN — known_limitations·고지 없음
        ],
    },
    {
        "name": "★반전 D — 혁신법 시행령(manifest 288773 의도적 유지) 정상 경로 = 288335 시행 본문 조문 71",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 71},              # WARN — v0.55.0 spec D의 반전(70→71)
            {"kind": "field_equals", "path": "annexes_count", "value": 8},                # WARN — 별표5의2 포함
            {"kind": "field_equals", "path": "effective_date", "value": "2026-09-11"},    # WARN — resolve된 현행 시행일
            {"kind": "field_equals", "path": "revision_notice",
             "value": "개정 반영: 시행일 2026-09-11 (manifest 기준 ID 288773 → 최신 ID 288335)"},  # WARN — 의도적 유지의 정상 표시
        ],
    },
    {
        "name": "★반전 E — 제35조의2(2026-09-11 시행)는 이제 조회되어야 함",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773:JO003502"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — v0.55.0 spec E의 반전
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "표적 — industry_tech_act 284363 문서레벨(정상 경로 eflaw = 감사 고지 억제)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:284363"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 72},              # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-09-18"},    # WARN
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN
            {"kind": "field_equals", "path": "warnings.0", "value": "LIVE 검증(2026-06-12): 조문 72·별표 없음."},  # WARN — 고지 억제 시 KL이 선두
        ],
    },
    {
        "name": "표적 — sme_tech_decree 289953 문서레벨(조문 51·별표 4)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:289953"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 51},              # WARN
            {"kind": "field_equals", "path": "annexes_count", "value": 4},                # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-09-22"},    # WARN
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN
        ],
    },
    {
        "name": "표적 — defense_tech_act 283941 문서레벨(조문 21)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283941"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 21},              # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-09-11"},    # WARN
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN
        ],
    },
    {
        "name": "표적 — facility_equipment_standard 2100000285744 문서레벨(조문 48·별표 14)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000285744"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 48},              # WARN — 제5조의2·제21조의2 신설
            {"kind": "field_equals", "path": "annexes_count", "value": 14},               # WARN — 별표 2의2 신설
            {"kind": "field_equals", "path": "effective_date", "value": "2026-09-30"},    # WARN
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN
        ],
    },
    {
        "name": "표적 — facility 신설 제5조의2(신속심의 대상의 지정) 도달",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000285744:JO000502"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). 프로브는 제목이 아니라 내용으로 설계한다(호스트 계정 메모리에
# 구 제목이 남아 있을 수 있음 — [[eval-probe-contamination]]). 폴백 경로를 겨냥한 라이브 프로브는 금지.
LEVEL_B_PROMPTS = [
    {
        "category": "★표적 A — 과기정통부 R&D 처리규정 신판 도달(신규 문안·차기 릴리스부터 verbatim 재사용)",
        "probe_prompt": "과학기술정보통신부 소관 연구개발사업에서 연구개발기관과 특수관계에 있는 자가 과제에 "
                        "참여할 때 지켜야 하는 규정이 있는지 도구로 원문을 확인해서 알려줘.",
        "expect_behavior": "msit_rnd_processing 신판(2100000285280·2026-09-18 시행·훈령 제325호) 제17조의2"
                           "(특수관계인 참여 관리) 인용. 규정이 없다고 답하거나 2023-08-24 구판·훈령 제242호를 "
                           "근거로 들면 실패(구판 폴백 잔존).",
    },
    {
        "category": "표적 B — 시설·장비 표준지침 신설 조문(신속심의)",
        "probe_prompt": "국가연구개발 시설·장비 도입 심의에서 신속심의 대상으로 지정받는 절차가 있는지 규정 근거와 함께 알려줘.",
        "expect_behavior": "국가연구개발 시설·장비의 관리 등에 관한 표준지침 제5조의2(신속심의 대상의 지정)·"
                           "별표 2의2(요청서) 인용. 부재 안내·날조 시 실패.",
    },
    {
        "category": "무회귀 C — 광역 검토 경로(v0.55.0 무회귀 문안 verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "시행령·사용 기준·별지 서식 인용 유지(검색 희석 0). 결과 수 감소·도달 실패가 보이면 "
                           "이번 manifest 갱신의 부수 효과를 의심한다.",
    },
]
