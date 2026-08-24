"""v0.54.0 배포 전 LIVE acceptance spec — 법령 시행 단계 차이 고지(상세 조회 경로 한정) + 감사 도구 수록.

읽는 법(비프로그래머용): 이번 릴리스는 감사에서 시행 단계 차이가 확인된 4개 규정의 **상세 조회 응답**에만
주의 문장 1개를 warnings 배열 맨 앞에 넣습니다. 검색 응답·규정 목록·검토 출처 추천에는 넣지 않습니다
(문면이 검색 응답 예산을 잠식하면 뒤쪽 결과가 잘려 검색 결과 수가 줄기 때문 — 로컬 실측 최대 -3건).
contract 0.36.0 유지·입력 스키마 무변·재연결 불요.

★본 spec이 검증하는 것 = 도구 응답(Level A)뿐입니다. 호스트 AI가 그 문장을 실제로 사용자에게 전달하는지는
배포 후 사람 eval(Level B)에서만 확인할 수 있습니다.

★러너(run.py)의 알려진 한계 2가지 — 이 spec의 PASS를 "배포해도 된다"로 곧장 읽지 말 것(구현 diff 적대검토
Codex MAJOR 3). ①러너는 도구 호출 중 발생한 모든 예외를 infra로 분류해 WARN 처리하므로, 구현 회귀에서 나온
결정론적 예외(ValidationError·TypeError 등)도 자동 BLOCK되지 않는다. ②fetched_ok는 "그 규정이 errors에
없음"만 검사하므로, 결과에도 오류에도 없는 조용한 누락(silent omission)을 도달로 PASS시킨다(v0.47.0에 기록된
기존 성질). 러너는 false-block-safe를 위해 이 설계를 유지하며(Andy 최우선 가치), 그 대가는 아래 운영 게이트
④의 후보 컨테이너 hard-fail 스모크와 사람 판정이 치른다 — 러너 WARN·PASS는 그 스모크를 통과한 뒤에만
배포 신호로 읽는다. 러너 자체 변경은 assert 5종 동결 규약(run.py·README·가드 테스트 동반) 대상이라 이번
릴리스의 단일 의도 밖이며, 별도 의도로 다룬다.

★고지의 시간 의존 한계(Codex MINOR): 판본 결합은 "어느 본문인가"를 맞출 뿐 "오늘이 며칠인가"를 반영하지 않습니다.
예컨대 2026-09-11이 지나도 24시간 TTL 캐시로 288773을 계속 받는 이용자에게는 "2026-09-11 시행 예정" 문면이 그대로
나갈 수 있고, 그때 그 부분은 이미 시행된 뒤입니다(남는 차이는 2027-01-01분). 문면이 "감사일 현재"를 명시해 오독을
줄이지만 근본 해소는 P3(본문을 시행일 기준으로 조회)와 2026-09-11 재감사(P4)에서 이뤄집니다.

★고지가 "판본에 결합"돼 있다는 점이 assert 해석에 중요합니다: 실제 조회한 판본(doc_id)이 감사 판본과
정확히 같을 때만 감사 문면이 나오고, 다르면 일반 주의 문장으로 바뀝니다. 따라서 아래 warnings.0 assert가
실패하면 두 가지 중 하나입니다 — (가) 구현 회귀 (나) 그 사이 법령이 새 판본으로 바뀜(=P4 재감사 트리거).
둘의 구분은 응답의 문면을 보면 즉시 됩니다(일반 주의 문장이면 (나)). 전건 WARN 설계이므로 배포를 막지 않습니다.

운영 게이트(배포 전 — 전건 통과 시에만 배포 승인 요청):
  ① pytest 전건 통과(가드 10종 포함: 4규정만 부착·62규정 미노출·검색 미부착·문면 verbatim·미설정 안전·
     반복 호출 비누적·list_rule_sets/suggest 미노출·3단 강등 승계·판본 불일치 분기·warnings[0] 위치).
  ② ★검색 무회귀 짝 비교 — 배포 직전 코드와 현행 라이브에서 **같은 질의 8건**(중소기업/산업기술/연구개발과제/
     연구개발기관/연구개발비/기술료/제재처분/연구보안)의 `returned`를 나란히 측정해 **델타 0**을 확인.
     1건이라도 감소하면 배포 중단(설계 전제가 깨진 것).
  ③ ★재감사 집합 정합 — 배포 직전 `scripts/audit_law_stage_diff.py`를 다시 돌려 기준선(`docs/audit_baseline/`)과
     대조한다. ★"DIFF 집합이 줄었으니 고지를 지운다"는 판단은 금지(구현 diff 적대검토 Codex MAJOR 2) — 조회·파싱
     실패가 UNKNOWN 승격으로 나타나면 DIFF 집합도 함께 줄기 때문에, 집합 축소만 보면 "확인 실패"를 "차이 해소"로
     뒤집어 읽게 된다. 판단 규칙:
       - 선행 조건: UNKNOWN 0건 · FORMAT_ONLY 집합이 기준선과 동일 · 서빙 MST가 기준선과 동일.
         하나라도 어긋나면 그 규정은 "판정 불가"이며 stage_notice를 그대로 두고 원인을 먼저 해소한다.
       - 제거는 그 규정의 새 판정이 **MATCH일 때만**(차이가 실제로 해소된 경우).
       - DIFF가 늘었으면 문면을 추가하거나 릴리스를 보류한다.
     (2026-08-25 실측 = MATCH 29 / FORMAT_ONLY 2 / DIFF 4 / UNKNOWN 0 · 기준선과 전건 동일 — `docs/audit_baseline/`에
      LIVE provenance 파일로 함께 커밋)
  ④ 후보 컨테이너(PORT=18080·host network) 부팅 406·serverInfo 0.54.0·cold LIVE 66규정 fan-out(done 66·errors 0)·
     hard-fail 스모크(law:283413 상세의 warnings[0]이 감사 문면·`list_rule_sets` total 66·매뉴얼 3-4·키 원문 0).
     ★health 200·406 도달만으로는 부족하다 — manifest(rule_sets.yaml)는 부팅이 아니라 각 업무 도구에서 lazy load되므로,
     YAML 오타는 health가 멀쩡한 채 검색·상세·목록만 무너지는 false-green으로 나타난다(Codex MINOR). 따라서 이번
     릴리스의 후보 스모크에서는 `list_rule_sets`와 검색 fan-out 실호출이 필수 항목이며, 하나라도 실패하면 후보를 폐기한다.
  ⑤ 롤백 태그 `:0.53.1-rollback`을 현행 라이브 이미지 ID에서 생성하고 가리키는 ID 확인 → 검증한 후보 이미지 ID를
     그대로 승격(재빌드 금지). 발동 기준·명령은 v0_53_1.py와 동일(태그명만 교체).
  ⑥ 스왑 후 — 외부 URL 정상·무키 406(도달 지표)·serverInfo 0.54.0·`list_rule_sets` 66·검색 errors 0·
     로그 `oc=` 0건(패턴 개수만). 배포 직후 검색 실패는 실패 캐시 TTL(300s)을 먼저 의심할 것(`wall_ms` 확인).
  ⑦ 관측은 신호 기반 — 스왑 후 최소 2회(직후·+1h 이상) 터널 프로브 전건 정상 + RestartCount 0 + traceback 0.

검증(asserts) 종류 5가지 고정(run.py):
  - fetched_ok / returned_not_below [회귀=BLOCK 후보] · absent_error_code / latency_under / field_equals [WARN]
"""

_ACT = (
    '주의(현행 시행분 누락·2026-08-23 감사): 이 서버가 제공하는 법률 제21347호 본문에는 법률 제21421호에 따라 2026-06-11 시행된 제2조제5호의2·제2조제10호, 제17조제1항, 제18조제2항 및 제32조제1항제5호의 개정 내용이 반영되어 있지 않습니다. 해당 부분은 국가법령정보센터에서 기준일을 지정해 확인하십시오. 이 문장은 감사일 현재 확인된 차이만 알리며, 열거되지 않은 부분이나 이후 판본의 정합성을 보증하지 않습니다.'
)
_DEC = (
    '주의(미시행분 선반영·2026-08-23 감사): 이 서버가 제공하는 대통령령 제36580호 본문에는 대통령령 제36525호에 따른 제35조의2·제36조·제37조의 2026-09-11 시행 예정 내용과 제16조제2항·제17조제1항·제4항·제5항·제31조·제41조제2항 각 호·제41조제3항·제5항의 2027-01-01 시행 예정 내용이 선반영되어 있습니다. 기준일별 본문은 국가법령정보센터에서 확인하십시오. 이 문장은 감사일 현재 확인된 차이만 알리며, 열거되지 않은 부분이나 이후 판본의 정합성을 보증하지 않습니다.'
)
_SME = (
    '주의(현행 시행분 누락·2026-08-23 감사): 이 서버가 제공하는 법률 제21289호 본문에는 법률 제21704호에 따라 2026-05-26 시행된 제2조제6호부터 제12호까지의 신설, 제27조의2제3항 삭제, 제27조의3(사업화 금융지원) 신설, 종전 제27조의3을 제27조의4로 이동·개정, 제27조의5 및 제28조의2 신설이 반영되어 있지 않습니다. 해당 부분은 국가법령정보센터에서 기준일을 지정해 확인하십시오. 이 문장은 감사일 현재 확인된 차이만 알리며, 열거되지 않은 부분이나 이후 판본의 정합성을 보증하지 않습니다.'
)
_IND = (
    '주의(인용 법률명 불일치·2026-08-23 감사): 이 서버가 제공하는 본문의 제5조제3항에는 종전 명칭 「지방자치분권 및 지역균형발전에 관한 특별법」이 남아 있습니다. 2026-06-02 시행된 법률 제21738호에 따른 현행 명칭은 「지방자치분권 및 균형성장에 관한 특별법」입니다. 이 문장은 감사일 현재 확인된 차이만 알리며, 열거되지 않은 부분이나 이후 판본의 정합성을 보증하지 않습니다.'
)

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
            {"kind": "latency_under", "value": 16.0},                                    # WARN — 기록용
        ],
    },
    {
        "name": "★검색 응답 미부착 증거 — '중소기업' 질의(고지 대상 sme_tech_act가 상위에 오는 질의)에서 결과 수 유지",
        "tool": "search_provision",
        "args": {"query": "중소기업"},
        "asserts": [
            # 회귀=BLOCK 후보. 하한 16의 근거: 2026-08-24·08-25 실측 returned=17이고, 문면이 검색에 새는
            # 회귀에서는 14로 떨어진다(당초 안 실측) — 하한을 14로 두면 그 회귀가 통과해버린다.
            # ★단일 절대 하한은 보조 신호일 뿐이다(Codex MINOR): 상위 법령 데이터 변동으로 자연 매치가 15가 되면
            # false BLOCK이고, 더 짧은 문구가 새어 16이 유지되면 false PASS다. 진짜 게이트는 운영 게이트 ②의
            # 8질의 구·신 짝 비교(델타 0)이며, 여기서 걸리면 먼저 짝 비교로 원인을 가른다.
            {"kind": "returned_not_below", "value": 16},
            {"kind": "absent_error_code", "value": "timeout"},                           # WARN
        ],
    },
    {
        "name": "고지 부착 — 혁신법 문서레벨(283413·warnings 첫 원소가 감사 문면 전체 일치)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283413"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                         # WARN
            {"kind": "field_equals", "path": "effective_date", "value": "2026-08-20"},   # WARN
            {"kind": "field_equals", "path": "warnings.0", "value": _ACT},               # WARN
        ],
    },
    {
        "name": "고지 부착 — 혁신법 조문 경로(JO0017·상세 3주입점 중 조문 분기 승계)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:283413:JO0017"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                         # WARN
            {"kind": "field_equals", "path": "warnings.0", "value": _ACT},               # WARN
        ],
    },
    {
        "name": "고지 부착 — 시행령 별표 경로(288773:BP000502·별표 분기 승계 + 기존 별표 제약은 뒤로 밀림)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:288773:BP000502"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                         # WARN
            {"kind": "field_equals", "path": "warnings.0", "value": _DEC},               # WARN
        ],
    },
    {
        "name": "고지 부착 + 조문 수 정정 — 중소기업 기술혁신 촉진법(281987·warnings.1이 정정된 49)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:281987"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                         # WARN
            {"kind": "field_equals", "path": "warnings.0", "value": _SME},               # WARN
            {"kind": "field_equals", "path": "warnings.1",
              "value": "LIVE 검증(2026-07-06): 조문 49·별표 없음."},                       # WARN
        ],
    },
    {
        "name": "고지 부착 + 조문 수 정정 — 산업기술혁신 촉진법(280041·warnings.1이 정정된 72)",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:280041"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                         # WARN
            {"kind": "field_equals", "path": "warnings.0", "value": _IND},               # WARN
            {"kind": "field_equals", "path": "warnings.1",
              "value": "LIVE 검증(2026-06-12): 조문 72·별표 없음."},                       # WARN
        ],
    },
    {
        "name": "★미대상 규정 무회귀 — 중소기업 기술혁신 촉진법 시행령(287505)의 warnings 첫 원소가 종전 제약 그대로",
        "tool": "get_provision_detail",
        "args": {"provision_id": "law:287505"},
        "asserts": [
            {"kind": "absent_error_code", "value": "not_found"},                         # WARN
            {"kind": "field_equals", "path": "warnings.0",
              "value": "LIVE 검증(2026-07-06): 조문 23·별표 4(검색·BP 상세 지원)."},        # WARN
        ],
    },
]

# Level B(배포 후 라이브 확인 + 사람 판정). 호스트가 warnings 첫 원소를 실제로 사용자에게 전달하는지가 이번 릴리스의 핵심 질문.
LEVEL_B_PROMPTS = [
    {
        "category": "★신규 커버리지 — 고지 소비(누락 방향)",
        "probe_prompt": "국가연구개발혁신법 제17조(연구개발기관의 변경 등)의 현재 조문 내용을 원문 그대로 알려줘.",
        "expect_behavior": "제17조 원문 인용과 함께 '2026-06-11 시행된 제17조제1항 개정이 본문에 반영되어 있지 않다'는 "
                           "취지의 주의를 사용자에게 전달하고, 확인 경로(국가법령정보센터·기준일 지정)를 안내할 것. "
                           "주의를 전혀 언급하지 않거나, 반대로 '이 조문 전체가 무효'처럼 과장하면 문면 재설계 후보.",
    },
    {
        "category": "★신규 커버리지 — 고지 소비(선반영 방향·법령 해석에 직접 영향)",
        "probe_prompt": "국가연구개발혁신법 시행령 제41조제2항에 따른 제재부가금 부과 기준을 알려줘.",
        "expect_behavior": "본문 값을 인용하되 '제41조제2항 각 호는 2027-01-01 시행 예정 내용이 선반영돼 있다'는 "
                           "주의를 함께 전달할 것(지금 적용값과 다를 수 있음). 선반영 사실을 빠뜨린 채 현행으로 "
                           "단정하면 이번 릴리스의 목적이 달성되지 않은 것.",
    },
    {
        "category": "무회귀 — cold 광역 fan-out 경로(v0.48.0 무회귀 B verbatim)",
        "probe_prompt": "국가연구개발과제의 연구개발비 정산 절차와 제출해야 하는 서류를 알려줘.",
        "expect_behavior": "66규정 fan-out 완주·기존 규정(연구개발비 사용 기준·시행령) 중심 유지 + "
                           "citation·footer 무회귀. 부분 timeout·누락 규정·오류 문면이 새로 보이면 회귀 의심. "
                           "고지 대상 4규정이 결과에 섞여도 검색 결과 수가 눈에 띄게 줄면 안 됨.",
    },
]
