"""v0.51.0 배포 전 LIVE acceptance spec — manifest 4건 현행화 + 상세 조회 미시행 시행일 고지.

읽는 법(비프로그래머용): 이번 릴리스는 ①manifest 4건 데이터 갱신(2026-08-20 시행 도래분 —
innovation_act 283849→283413·innovation_decree 288335→288773·innovation_rule 286879→289003·
sector_kt_decree 264735→288777) ②get_provision_detail(law 한정) 조건부 additive 필드 1종
(fetched_detail_effective_date_notice — fetch된 lawService 상세의 시행일자가 미래일 때만 발화·
contract 0.35.0→0.36.0 §5.42·입력 스키마 무변·재연결 불요)입니다.

★시행일 게이트(v0.49.0 패턴 준용): 본 spec은 2026-08-20 시행 도래 후 실행 전제. 문서레벨
4체크의 WARN 조합 — effective_date == "2026-08-20"(신판 식별) + revision_notice ==
"<missing>"(스냅샷=현행 일치) + resolve_fallback_notice == "<missing>"(폴백 우회 검출) +
upcoming_revision == "<missing>"(미래행 우회 검출).

★신규 게이트 = fetched_detail_effective_date_notice == "<missing>": 신 manifest MST가 현행
상세를 서빙하면 미발화가 정상. 이 필드가 발화하면 C12 재발 신호(합본 MST가 미래 분리시행분
본문을 서빙)이므로 배포 보류하고 scripts/audit_manifest_effective_dates.py로 전수 감사 후
사람 판정하십시오. ★구 ID(283849 등) 조회가 not_found인 것은 회귀가 아니라 정상입니다
(manifest 갱신으로 구 ID 직접 경로 차단 — v0.50.0 not_found 문면이 재검색 복구를 안내).

resolve 캐시(86,400s) 오염 회피: 러너는 새 프로세스(fresh client)로 실행(run.py 1회 구동 기본 충족).

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok         : 지정 규정(rule_set_id)이 오류 없이 조회됨.                    [회귀=BLOCK 후보]
  - returned_not_below : 결과 개수가 value 이상(recall 비회귀).                        [회귀=BLOCK 후보]
  - absent_error_code  : 지정 오류코드가 0건.                                          [WARN — 차단 안 함]
  - latency_under      : 응답이 value초 미만.                                          [WARN — 기록용]
  - field_equals       : 응답의 특정 경로 값이 value와 같음("<missing>"=키 부재).       [WARN — 사람 판정 참고]
"""

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out 대형 규정 도달 + recall(릴리스 간 동일 문안)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},                # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                   # 회귀=BLOCK 후보(신 MST 288773 경유)
            {"kind": "returned_not_below", "value": 10},                                  # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                            # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — 대량이면 infra 여부 사람 판정
            {"kind": "latency_under", "value": 16.0},                                     # WARN — 기록용
        ],
    },
    {
        "name": "표적 — innovation_act 신판 문서레벨 직접 도달(283413·시행일 게이트 + ★신규 고지 미발화)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283413"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 신 ID 실도달
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN — infra 구분 증거
            {"kind": "field_equals", "path": "articles_count", "value": 42},              # WARN — 사전 실측(2026-08-20) 구조 잠금
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN — ★신판 식별 + 시행일 게이트
            {"kind": "field_equals", "path": "revision_notice", "value": "<missing>"},    # WARN — 스냅샷=현행 일치로 미발화 정상
            {"kind": "field_equals", "path": "resolve_fallback_notice", "value": "<missing>"},  # WARN — 폴백 우회 검출
            {"kind": "field_equals", "path": "upcoming_revision", "value": "<missing>"},  # WARN — 미래행 우회 검출
            {"kind": "field_equals", "path": "fetched_detail_effective_date_notice", "value": "<missing>"},  # WARN — ★발화 = C12 재발 신호(위 docstring)
        ],
    },
    {
        "name": "표적 — innovation_decree 신판 문서레벨(288773·조문 71·별표 8건[별표5의2 신설] 구조 잠금)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 71},              # WARN — 사전 실측(구 69 → 신 71)
            {"kind": "field_equals", "path": "annexes_count", "value": 8},                # WARN — 별표5의2 신설(7→8)
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN
            {"kind": "field_equals", "path": "fetched_detail_effective_date_notice", "value": "<missing>"},  # WARN
        ],
    },
    {
        "name": "표적 — 신설 별표5의2 BP000502 도달(연구보안 전담기관 행정처분·3,302자 소형 전문)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773:BP000502"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN — 가지별표 채번 정상
            {"kind": "absent_error_code", "value": "annex_unavailable_parse_failed"},     # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 소형은 전문 수록
        ],
    },
    {
        "name": "표적 — innovation_rule·sector_kt_decree 신판 조합(문서레벨 JO 경유 대신 rule 문서레벨)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:289003"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 4},               # WARN — 사전 실측(구판도 4 — 구조 지표)
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN — ★신판 식별 증거
            {"kind": "field_equals", "path": "fetched_detail_effective_date_notice", "value": "<missing>"},  # WARN
        ],
    },
    {
        "name": "표적 — sector_kt_decree 신판 문서레벨(288777·조문 13)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288777"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "articles_count", "value": 13},              # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN — ★신판 식별(구 2024-08-07과 구분)
            {"kind": "field_equals", "path": "fetched_detail_effective_date_notice", "value": "<missing>"},  # WARN
        ],
    },
    {
        "name": "표적 — 혁신법 제2조 JO verbatim(신·구 판 분기 조문 — 현행판 정상 서빙 증거)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283413:JO0002"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                       # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN — 제2조(정의)는 소형 조문
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). 무회귀 문안은 v0.48.0 spec verbatim 재사용
# (릴리스 간 A/B 비교 기준 유지 — [[eval-probe-design-standard]]).
LEVEL_B_PROMPTS = [
    {
        "category": "표적 A — 혁신법 신판 도달·9월판 오염 부재(신규 문안·차기 릴리스부터 verbatim 재사용)",
        "probe_prompt": "국가연구개발혁신법 제2조 정의 조항에 어떤 용어들이 정의되어 있는지 도구로 "
                        "원문을 확인해서 목록으로 알려줘. 지금 시행 중인 판은 언제부터 시행된 것인지도 확인해줘.",
        "expect_behavior": "law:283413 경유 현행판 제2조 정의 목록 + 시행일 2026-08-20 안내. "
                           "'정부납부기술료' 정의(제10호)가 목록에 나타나면 9월판(283849) 오염 = 실패. "
                           "fetched_detail_effective_date_notice 미발화(현행 서빙)가 정상.",
    },
    {
        "category": "표적 B — 신설 별표5의2 도달(연구보안 전담기관 행정처분)",
        "probe_prompt": "연구보안 전담기관이 업무를 부실하게 수행했을 때 받는 행정처분의 세부기준을 "
                        "규정 근거와 함께 알려줘.",
        "expect_behavior": "혁신법 시행령 별표5의2(BP000502·제48조의2제4항 관련) 도달 + 본문 근거 인용. "
                           "별표 부재 안내·날조 발생 시 실패(신설 별표 발견성 검증).",
    },
    {
        "category": "무회귀 C — cold 광역 fan-out 경로(v0.48.0 무회귀 B verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out 완주·기존 규정(연구개발비 사용 기준·시행령) 중심 유지 + "
                           "citation·footer 무회귀. 부분 timeout·누락 규정·오류 문면이 새로 보이면 "
                           "회귀 의심.",
    },
]
