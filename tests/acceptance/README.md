# 배포 전 LIVE acceptance (개선점 자동 검증)

업데이트를 **배포하기 전에**, 신코드를 로컬에서 실행해 LIVE 법령정보 API(law.go.kr) 대상으로
"이번 버전의 개선이 실제로 살아있는지"를 자동으로 확인하는 도구입니다. (배포 후 라이브 커넥터에서
사람이 하던 수동 테스트의 **결정론적(숫자·존재여부) 부분**을 자동화.)

## 실행

```
/Users/andykim/my_project/venv/bin/python tests/acceptance/run.py 0.2.7
```

또는 스킬로: `/regs-acceptance 0.2.7` (배포 직전 `/regs-release-gate`도 정적 검증 통과 후 이 단계를 호출).

종료 코드: `0`=PASS · `2`=WARN(비차단) · `3`=BLOCK 후보(재현 회귀) · `4`=SKIP(키 없음) · `5`=spec 오류.

## 핵심 원칙 — "정상 배포를 막지 않는다" (false-block 회피)

서비스 끊김없음이 최우선이므로, **LIVE/네트워크 변동성이 정상 배포를 막으면 안 됩니다.** 그래서:

- **자동 BLOCK은 단 2가지 신호**일 때만, 그나마 **2회 시도에서 재현**될 때만:
  1. `대형 규정 미도달`(fetched_ok 실패) — 어떤 규정이 조회에서 빠짐.
  2. `결과 개수 명백 감소`(returned_not_below 실패) — 검색 결과가 기준 미만.
- **skip(timeout)·latency 초과는 BLOCK 아님(WARN)** — 정상 동작에서도 네트워크 변동으로 가끔 발생.
- **상위 API 장애(law.go.kr 다운)** = 전건 `parse_failed`/연결오류 → infra로 보고 **WARN**(회귀 아님).
- **LAW_API_KEY 없으면 SKIP**(키 없는 환경에서 막지 않음).
- **최종 BLOCK 판정은 사람**(메인 스레드). 이 도구는 증거 + 분류만 제공합니다.

즉 "PASS면 안심, WARN이면 증거 보고 사람이 판단, BLOCK이면 재현 회귀 의심 — 사람이 확인" 입니다.

## 새 버전 spec 만드는 법 (비프로그래머)

1. `v0_2_7.py`를 복사해 `v0_2_8.py` 등으로 만듭니다.
2. `CHECKS` 안의 항목만 이번 버전 개선에 맞게 고칩니다. 각 항목:
   ```python
   {"name": "사람이 읽을 이름", "tool": "search_provision", "args": {"query": "키워드"},
    "asserts": [ ...검증 목록... ]}
   ```
3. 검증(`asserts`) 종류는 **5가지로 고정**(새 종류를 임의로 늘리면 `test_acceptance_spec.py`가 실패):

   | kind | 뜻 | 차단? |
   |---|---|---|
   | `fetched_ok` | `{"kind":"fetched_ok","rule_set_id":"ict_rnd_management"}` — 그 규정이 오류 없이 조회됨 | 회귀=BLOCK 후보 |
   | `returned_not_below` | `{"kind":"returned_not_below","value":5}` — 결과 개수 ≥ value | 회귀=BLOCK 후보 |
   | `absent_error_code` | `{"kind":"absent_error_code","value":"timeout"}` — 그 오류코드 0건 | WARN |
   | `latency_under` | `{"kind":"latency_under","value":16.0}` — 응답 < value초 | WARN |
   | `field_equals` | `{"kind":"field_equals","path":"results.0.content_format","value":"plain_text_verbatim"}` | WARN |

4. 규정 확대처럼 결과 개수가 정당히 변하는 버전은 `returned_not_below` 값을 **넉넉히 낮게**(붕괴만 잡게)
   두고, **`fetched_ok`(규정 id) 중심**으로 쓰세요 — 숫자 baseline 관리 부담이 적고 안정적입니다.

## Level A / Level B 경계

- **Level A (이 도구가 자동 검증)** = 도구가 내보내는 **응답 그 자체**(값·개수·도달/부재·형태). 결정론적.
  예: v0.2.7 안정성(대형 규정 도달·skip·returned), 규정 확대(신규 규정 도달), 별표 size-tier 값.
- **Level B (자동 불가 — 사람이 배포 후 수동)** = 도구 응답을 받은 **호스트 LLM의 행동**. 비결정·하니스 의존.
  예: v0.2.1 별표 정확 선택, v0.1.9 degraded 시 재호출, 범위 외 정직성.
  → spec의 `LEVEL_B_PROMPTS`에 `{"probe_prompt":..., "expect_behavior":...}`를 적으면, 러너가
  **배포 후 라이브 커넥터에서 사람이 수동 확인할 프롬프트로 출력만** 합니다(게이트 판정 아님). 배포 전
  라이브 커넥터는 구버전을 서빙하므로 신버전 Level B는 본질적으로 배포 후에만 관측 가능합니다.

## 한계 (알아둘 것)

- 모든 check를 한 프로세스에서 돌려, **첫 check의 1회째만 진짜 cold**(이후는 캐시 warm). `fetched_ok`·
  `returned_not_below`는 캐시와 무관하게 정답을 검증하므로 신뢰 가능하나, latency/skip 신호는 첫 check에서
  주로 잡힙니다(그래서 둘 다 WARN).
- 보안: 키 값·URL은 어떤 형태로도 출력하지 않습니다(예외는 종류 이름만).
- 실행은 항상 shared venv(`/Users/andykim/my_project/venv/bin/python`)로 — repo 루트의 `.venv`는 사용 금지.
