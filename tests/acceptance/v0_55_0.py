"""v0.55.0 배포 전 LIVE acceptance spec — 시행일 기준 조회 전환(target=law → target=eflaw&efYd=).

읽는 법(비프로그래머용): 이번 릴리스는 법령 35개의 조문·별표 본문을 「공포된 문서 전체」가 아니라
「오늘 실제로 시행 중인 본문」에서 가져오도록 바꿉니다. 검색과 상세 조회를 함께 전환합니다.
시행일 기준 조회가 실패하면 곧바로 종전 방식으로 되돌아가므로(폴백), 실패해도 오늘보다 나빠지지 않습니다.
contract 0.36.0 유지 · 입력 스키마 무변 · 커넥터 재연결 불요.

★본 spec이 검증하는 것 = 도구 응답(Level A)뿐입니다. 호스트 AI 행동은 배포 후 사람 eval(Level B).

★증거 계층의 한계(구현 diff 적대검토): 조회 경로(stage_basis)는 응답에 노출하지 않으므로(노출하면
계약 additive가 되어 규격 번호를 올려야 함), 응답만으로 "eflaw로 서빙됐다"를 직접 증명할 수 없습니다.
아래 체크는 **내용 지문**(조문 수·특정 조문의 존재/부재·감사 고지 억제)으로 간접 증명합니다.
직접 증거는 운영 게이트 ④(모의 서버 stub의 요청 파라미터)와 ⑦(서버 로그의 경로별 집계)이 담당합니다.

★러너(run.py)의 알려진 한계 2가지는 v0.54.0 spec에 기록된 그대로입니다 — ①모든 예외를 infra로 분류해
WARN 처리 ②fetched_ok는 "errors에 없음"만 검사. 러너 PASS를 곧장 "배포해도 된다"로 읽지 말고, 아래 운영
게이트를 통과한 뒤에만 배포 신호로 읽습니다.

★★시간 의존 기준값 주의: 2026-09-11부터 혁신법 시행령의 현행 판본이 288335로 바뀌면서
`articles_count`가 70 → 71이 되고 제35조의2가 시행돼 조회 가능해집니다. 그 이후 이 spec을 그대로 돌리면
아래 체크 D·E가 실패하는데 이는 회귀가 아니라 **정상 전환**입니다(전건 WARN 설계라 배포를 막지 않습니다).
그 시점에는 기준값을 71/존재로 바꾼 v0.56.0 spec을 씁니다.

운영 게이트(배포 전 — 전건 통과 시에만 배포 승인 요청):
  ① pytest 전건 통과(신규 가드 tests/test_stage_eflaw.py 44종 포함: 제로콜 차단·전용 예산·4중 판정·
     실패 6종 폴백·인증 실패 전파·서킷 브레이커·sticky fallback 금지·본문 무오염·efYd 정규화·재평가 제거·
     고지 억제/폴백 가시화/내부 필드 미노출).
  ② ★검색 델타 2집합 — (가) 비영향 8질의(중소기업/산업기술/연구개발과제/연구개발기관/연구개발비/기술료/
     제재처분/연구보안)를 구·신 코드로 나란히 돌려 **규정·조문 단위 결과가 완전 동일**할 것(건수만 비교하면
     다른 규정의 동명 토큰이 감소를 가린다). (나) 변경 조문 표적 질의로 방향을 잠글 것 —
     「균형성장」 도달 · 「지역균형발전」 미도달이 정답 · 제27조의4 출현 · 미시행 제35조의2 소실.
  ③ ★재감사 정합 — `scripts/audit_law_stage_diff.py` 재실행 후 기준선(`docs/audit_baseline/`)과 대조.
     UNKNOWN 1건이라도 나오면 배포 보류. (감사 자체는 서버 런타임과 무관한 read-only 도구.)
  ④ ★eflaw 단독 장애 모의시험(3모드) — 실제 배포할 후보 이미지를 stub 주소로 기동해 측정.
     (가) 즉시 오류 모드: 전체 검색 8초 이내 완주 (나) 응답 정지 모드: **3회 측정 최악값 12초 이내**
     (다) 저속 흐름 모드: 후속 검색이 작업자 고갈 없이 완주.
     ★(나)가 한 번이라도 12초를 넘으면 **전건 35규정 → 오차 4규정(canary)으로 축소**해 배포하며,
     이 분기는 PyPI 게시 전에 끝낸다(공개 채널은 롤백이 불가능하므로). 범위를 바꾸면 새 산출물이므로
     게이트 전체를 다시 통과시킨다.
  ⑤ 후보 컨테이너 cold fan-out 3회 — 전부 done=66 · skipped=0 · errors=0 · wall_ms ≤ 8,000.
     로그의 경로별 집계로 시행일 기준 성공 35건 · 폴백 0건을 함께 확인.
  ⑥ admrul 31규정 짝 비교 동일(이번 전환 대상 아님 — 무회귀 증명).
  ⑦ 배포 후 관측 3시점 — 즉시 · 실패 기억(300초)이 실제로 만료된 뒤 · +1시간.
     RestartCount 0 · traceback 0 · 경로별 집계에 폴백 잔존 없음 · 자동 회복 확인.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok / returned_not_below [회귀=BLOCK 후보] · absent_error_code / latency_under / field_equals [WARN]
"""

# 2026-08-25 LIVE 실측 앵커(sweep2·직접 조회) — eflaw 경로에서만 성립하는 값들
_SME_JO2704_TITLE = "사업화계정의 설치 및 재원"      # 공포 합본에는 존재하지 않는 조문
_SME_JO2703_TITLE = "사업화 금융지원"                # 합본은 구 조문 제목(번호는 동일)

CHECKS = [
    {
        "name": "무회귀 핵심 — 광역 '연구개발비' 66규정 fan-out 대형 규정 도달 + recall(릴리스 간 동일 문안)",
        "tool": "search_provision",
        "args": {"query": "연구개발비"},
        "asserts": [
            {"kind": "fetched_ok", "rule_set_id": "rnd_funding_standard"},               # 회귀=BLOCK 후보
            {"kind": "fetched_ok", "rule_set_id": "innovation_decree"},                  # 회귀=BLOCK 후보
            {"kind": "returned_not_below", "value": 10},                                 # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                           # WARN
            {"kind": "absent_error_code", "value": "parse_failed"},                      # WARN
            # WARN — 기록용. eflaw는 law보다 규정당 중앙값 +369ms 느리므로(실측) 상한을 16→18로 완화.
            {"kind": "latency_under", "value": 18.0},
        ],
    },
    {
        "name": "무회귀 — '중소기업' 질의 결과 수 유지(전환으로 조문 3개가 늘어나므로 감소하면 회귀)",
        "tool": "search_provision",
        "args": {"query": "중소기업"},
        "asserts": [
            {"kind": "returned_not_below", "value": 16},                                 # 회귀=BLOCK 후보
            {"kind": "absent_error_code", "value": "timeout"},                           # WARN
        ],
    },
    {
        "name": "★A 전환 증거 — 중소기업법 제27조의4 도달(공포 합본에는 없고 시행 본문에만 있는 조문)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987:JO002704"},
        "asserts": [
            # ★이 조문이 나오는 것 자체가 시행일 기준 본문을 서빙했다는 내용 지문이다.
            {"kind": "field_equals", "path": "title", "value": _SME_JO2704_TITLE},        # WARN
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
        ],
    },
    {
        "name": "★B 전환 증거 — 중소기업법 제27조의3이 신설 조문으로 교체(번호는 같고 내용이 바뀐 함정)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987:JO002703"},
        "asserts": [
            # 합본이면 구 조문 제목이 나온다 — 제목 하나로 구·신 판본이 갈린다.
            {"kind": "field_equals", "path": "title", "value": _SME_JO2703_TITLE},        # WARN
        ],
    },
    {
        "name": "★C 전환 증거 — 중소기업법 문서레벨 조문 수 52(공포 합본은 49)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987"},
        "asserts": [
            {"kind": "field_equals", "path": "articles_count", "value": 52},              # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-07-01"},    # WARN
        ],
    },
    {
        "name": "★D 전환 증거 — 혁신법 시행령 조문 수 70(합본은 71 · 미시행 제35조의2 제외) ※09-11부터 71",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773"},
        "asserts": [
            # ★2026-09-11 이후에는 71이 정답(정상 전환) — 위 '시간 의존 기준값 주의' 참조.
            {"kind": "field_equals", "path": "articles_count", "value": 70},              # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN
        ],
    },
    {
        "name": "★E 전환 증거 — 미시행 제35조의2는 조회되지 않아야 함(합본에서는 조회됨) ※09-11부터 조회 가능",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773:JO003502"},
        "asserts": [
            # 시행 전 조문이 현행처럼 제공되던 오류의 해소 증거. 09-11 이후에는 이 체크가 반전된다.
            {"kind": "field_equals", "path": "errors.0.code", "value": "not_found"},      # WARN
        ],
    },
    {
        "name": "★F 전환 증거 — 산업기술혁신 촉진법 제5조의 인용 법률명이 현행 명칭",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:280041:JO0005"},
        "asserts": [
            # ★한계(최종 재검증 라운드 지적): assert 5종에는 부분 문자열 검사가 없어 이 체크는
            # 도달·형식만 본다. 현행 명칭('균형성장') 도달과 구 명칭 미도달의 실증은 운영 게이트
            # ②(나)의 표적 질의 짝 비교가 전담한다 — 이 체크만으로 F를 통과로 읽지 말 것.
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
            {"kind": "field_equals", "path": "content_format", "value": "plain_text_verbatim"},  # WARN
        ],
    },
    {
        "name": "★G 고지 억제 — 혁신법 문서레벨 warnings가 비어야 함(감사 문면 억제의 직접 증거)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283413"},
        "asserts": [
            # innovation_act는 known_limitations가 없어, eflaw 억제가 작동하면 warnings는 빈 배열이다.
            # 폴백이면 warnings.0에 감사 문면 또는 폴백 안내가 실려 불일치 → 폴백 신호로 읽는 WARN.
            # (종전 체크는 warnings를 검사하지 않아 억제 실패도 통과했다 — 최종 재검증 라운드 지적.)
            {"kind": "field_equals", "path": "warnings.0", "value": "<missing>"},         # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN
        ],
    },
    {
        "name": "무회귀 — admrul 트랙(이번 전환 대상 아님) 상세 조회 정상",
        "tool": "get_provision_detail",
        "args": {"provision_id": "admrul:2100000283100"},
        "asserts": [
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},    # WARN
            {"kind": "absent_error_code", "value": "not_found"},                          # WARN
        ],
    },
]

LEVEL_B_PROMPTS = [
    {
        "category": "★표적 — 시행 본문 정확성(번호가 같고 내용이 바뀐 함정)",
        "probe_prompt": "2026-08-25 현재 중소기업 기술혁신 촉진법 제27조의3은 어떤 내용의 조문인지 알려줘.",
        "expect_behavior": "제27조의3을 '사업화 금융지원'(2026-05-26 시행 신설)으로 답하고, 종전 제27조의3이 "
                           "제27조의4로 이동했음을 언급할 수 있어야 한다. 구 조문(사업화계정 설치·재원)을 "
                           "제27조의3의 현행 내용으로 답하면 전환 실패 또는 폴백 상태다.",
    },
    {
        "category": "★표적 — 미시행 조문이 현행처럼 제공되지 않는가",
        "probe_prompt": "2026-08-25 현재 국가연구개발혁신법 시행령에 연구개발성과의 교부·열람을 위한 기탁에 관한 조문이 있는지 알려줘.",
        "expect_behavior": "현행 시행령에서 확인되지 않는다고 답해야 한다(제35조의2는 2026-09-11 시행 예정). "
                           "제35조의2를 현행 조문으로 단정해 인용하면 미시행 오염이 남아 있는 것이다.",
    },
    {
        "category": "무회귀 — 광역 검토 경로",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "v0.54.0 eval과 동일하게 시행령·사용 기준·별지 서식을 인용해야 한다(검색 희석 0). "
                           "결과 수 감소·도달 실패가 보이면 전환의 부수 효과를 의심한다.",
    },
]
