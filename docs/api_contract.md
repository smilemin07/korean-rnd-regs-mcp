# korean-rnd-regs-mcp API Contract

- contract_version: **0.2.0** (0.1.0 첫 publish → 0.2.0 minor bump, §6 변경 이력 참조)
- 작성일: 2026-05-24 (0.2.0 개정: 2026-06-04)
- semver 정책: 0.x.x 대역은 unstable signal — minor bump(0.1.0 → 0.2.0)도 breaking change 허용. v0.2 가지조문 확장 시 0.2.0 minor bump로 자연스럽게 처리 (1.0.x 유지 시 2.0 major bump 필요했음)
- 변경 정책: 본 문서 변경은 외부 사용자 코드·Claude Desktop 캐시·README 예시를 깰 수 있으므로 0.1.0 publish 이후 신중히 (§6 참조)

## 1. 목적

본 문서는 korean-rnd-regs-mcp가 (a) MCP 클라이언트에게 노출하는 도구 인터페이스와 (b) 내부적으로 사용하는 국가법령정보 OpenAPI 호출 규약을 명세한다.

## 2. 국가법령정보 OpenAPI 매핑

### 2.1 법령 (law)

| 작업 | endpoint | 핵심 응답 필드 |
|---|---|---|
| 검색 | `GET https://www.law.go.kr/DRF/lawSearch.do?target=law&query=<keyword>&OC=<api_key>&type=XML` | `법령ID`, `법령일련번호`(=MST 후보), `법령명한글`, `법령구분명`, `시행일자`, `공포일자`, `소관부처명` |
| 상세 | `GET https://www.law.go.kr/DRF/lawService.do?target=law&MST=<법령일련번호>&OC=<api_key>&type=XML` | `<기본정보>` 안에 `법령ID`·`법령명_한글`·`법종구분`·`소관부처`·`시행일자`·`공포일자`; `<조문>` wrapper 아래 `<조문단위>` list (`조문번호`/`조문제목`/`조문내용`); 부칙·별표 정보 |

- **두 ID(`법령ID`·`법령일련번호`) 모두 보존 필수.** 검색에서 받은 `법령일련번호`를 상세조회의 `MST` 파라미터로 그대로 사용한다.
- `MST` vs `ID`: `lawService.do`는 둘 중 하나로 호출 가능. 본 plan은 **MST** 사용 (korean-law-mcp 기존 패턴 + 검색 응답에서 항상 제공됨). `ID`만 보존하고 MST를 버리면 상세조회 깨짐.

#### 2.1.1 search ↔ detail XML schema 불일치 (중요 — 2026-05-24 발견)

법령 search 응답과 detail 응답은 동일 도메인이지만 **XML field 이름이 다름**. 단순 복사 시 detail 파싱이 빈 문자열로 실패하는 silent bug 발생. 다음 매핑을 정확히 사용:

| 의미 | search 응답 (lawSearch.do) | detail 응답 (lawService.do) |
|---|---|---|
| 법령명 | `법령명한글` | `법령명_한글` (underscore!) |
| 법령 분류 | `법령구분명` | `법종구분` (다른 이름) |
| 소관부처 | `소관부처명` | `소관부처` (명 없음) |
| 법령일련번호 | `법령일련번호` (응답 있음) | (응답 없음 — 호출 param `MST` 그대로 사용) |
| 조문 list path | (search는 list 없음) | `.//조문단위` 49개 (`.//조문`은 wrapper 1개만) |

본 프로젝트의 `live_api.py` `LawApiClient` dataclass는 두 응답을 흡수하여 **일관된 dict key (`법령명한글`·`법령구분명`·`소관부처명` 등)로 반환**한다 — 외부 사용자는 schema 차이를 신경 쓸 필요 없음. 단 내부 구현 시 위 매핑을 반드시 적용.

### 2.2 행정규칙 (admrul)

| 작업 | endpoint | 핵심 응답 필드 |
|---|---|---|
| 검색 | `GET https://www.law.go.kr/DRF/lawSearch.do?target=admrul&query=<keyword>&OC=<api_key>&type=XML` | `행정규칙일련번호`(=상세조회의 ID), `행정규칙ID`(=LID, 별도 식별자), `행정규칙명`, `소관부처명`, `제정일자`, `시행일자` |
| 상세 | `GET https://www.law.go.kr/DRF/lawService.do?target=admrul&ID=<행정규칙일련번호>&OC=<api_key>&type=XML` | 조문, 부칙, `별표내용`(있을 경우 본문, 없으면 첨부파일 링크만) |

- **상세조회 시 `행정규칙일련번호` 사용** (= `ID` 파라미터). `행정규칙ID(LID)`와 혼동 금지.
- 별표(`별표내용`): 응답 필드에 본문이 있으면 그대로 반환, 비어있거나 첨부파일(HWP/PDF)만 있으면 `source_url`로 안내 (plan b).
- 행정규칙 XML schema는 법령과 다르므로 **파서 별도 유지** (단일 파서로 통합 시 크래시 위험).

### 2.3 시행령

- target=law로 동일 검색되며 응답의 `법령구분명`이 "대통령령"인 항목.
- provision_id는 `law:` prefix 그대로 사용 (별도 doc_type 추가 없음).

### 2.4 MVP에서 사용하지 않는 endpoint

- 판례(`target=prec`): korean-law-mcp 담당, 본 server는 제외.
- 일반 법률 검색 (예: 민법, 행정절차법): korean-law-mcp 담당.

## 3. provision_id 포맷

### 3.1 단일 형식

```
{doc_type}:{doc_id}[:{unit_id}]
```

| 필드 | 허용 값 | 비고 |
|---|---|---|
| `doc_type` | `law` 또는 `admrul` | 소문자, MVP에서 두 값만 (확장 시 §6 minor bump) |
| `doc_id` | 숫자열 문자열 | doc_type=law → `법령일련번호`(MST); doc_type=admrul → `행정규칙일련번호`(ID) |
| `unit_id` (선택) | `JO` + 4자리 이상 숫자(조문, 예: `JO0003`) **또는** `BP` + 4자리 이상 숫자(별표, 예: `BP0001`) | 생략 시 document-level reference |

**JO vs BP**: LIVE 검증에서 일부 행정규칙(예: "국가연구개발사업 연구개발비 사용 기준" ID=2100000278740)은 조문 0개 + 별표 30개로 구성됨을 발견. 따라서 별표 단위 reference가 필요. `unit_type(unit_id)` 헬퍼로 article/annex/document 판정.

### 3.2 예시

```
law:260807                       # 국가연구개발혁신법(MST=260807, 2025-02-28 시행) 전체
law:260807:JO0003                # 동 법 제3조
admrul:2100000023234             # 행정규칙(ID=2100000023234) 전체
admrul:2100000023234:JO0007      # 동 행정규칙 제7조
admrul:2100000278740:BP0001      # "연구개발비 사용 기준" 별표 1 (기본사업연구개발비계상기준)
admrul:2100000278740:BP0030      # 동 행정규칙 별표 30
```

### 3.3 doc_type 선행 강제 이유

- a (법령 상세) vs b (행정규칙 상세) **dispatch 라우팅 키**로 사용.
- doc_type 없이 ID만 받으면 어느 endpoint를 호출할지 결정 불가 → silent failure 또는 잘못된 endpoint 호출.

### 3.4 구현

- 모듈: `src/korean_rnd_regs_mcp/provision_id.py`
- 공개 API: `parse(str) -> ProvisionId`, `build(doc_type, doc_id, unit_id=None) -> str`, `unit_type(unit_id) -> str` (article/annex/document), `ProvisionId` dataclass, `InvalidProvisionId` 예외, `CONTRACT_VERSION` 상수.
- 테스트: `tests/test_provision_id.py` (정상 조문 3건 + 별표 2건 + malformed 6건 + helper 4건 + round-trip 3건).

## 4. 표준 오류 코드 + envelope

### 4.1 envelope shape

모든 MCP 도구의 오류는 응답 최상위 `errors` 필드(list)에 적재. 단일 오류도 list로 표현하여 partial failure(예: search_provision에서 일부 rule_set 실패)와 일관성 유지.

```
{
  "errors": [
    {
      "code": "<표준 코드 — 아래 §4.2>",
      "message": "<오류 설명. LAW_API_KEY 값은 항상 마스킹>",
      "rule_set_id": "<선택 — search_provision 등 multi-doc 도구에서만>"
    },
    ...
  ],
  "contract_version": "0.2.0",
  "disclaimer": "본 결과는 검토 후보일 뿐 법률 판단이 아닙니다. 출처를 직접 확인하세요."
}
```

성공 응답에는 `errors`가 없거나 빈 list. 도구별 success 응답 schema는 별도 정리 예정 (v0.2 우선순위).

### 4.2 표준 코드

| 코드 | 의미 | 발생 시점 |
|---|---|---|
| `auth_failed` | OpenAPI 인증 실패 | API 응답 401/403 또는 본문에 인증 오류 |
| `rate_limited` | rate limit 초과 | API 응답 429 또는 일일 호출 제한 도달 |
| `parse_failed` | 응답 파싱 실패 | Content-Type이 XML 아님 (예: HTML 에러 페이지), XML 파싱 예외, 또는 네트워크 오류 (재시도 모두 실패; message는 type name만 노출하여 URL/key 누설 차단) |
| `not_found` | 검색 결과 0건 또는 상세조회 대상 없음 | API 응답에 항목 없음 |
| `invalid_provision_id` | provision_id 포맷 위반 | `parse()` 호출 시 `InvalidProvisionId` 발생 |
| `invalid_query` | search_provision의 query가 공백 제외 2자 미만 | 반영 — 무차별 매칭 방어 |

### 4.3 보안 정책

- LawApiError.message는 `_request_with_retry`에서 type name만 사용하여 URL/query params (특히 `OC=<key>`)가 절대 포함되지 않음 (source layer 차단).
- main.py의 도구 응답 출력 직전 `_sanitize_error_message`가 LAW_API_KEY 값을 추가 redact (defense-in-depth).
- 도구 응답의 어느 필드에도 LAW_API_KEY 값·앞자리·hash 미포함.

## 5. 응답 길이 정책

- `search_provision`의 `snippet`: 각 결과당 **≤ 2000자**
- `get_provision_detail` 본문: 길이 제한 없음. 단 별표는 `source_url` 안내로 대체 가능 (§2.2).
- 동기: Claude Code MCP는 도구 응답이 일정 크기 초과 시 경고·truncation 가능 — `search_provision`은 후보 제시용이므로 snippet으로만 노출하고 전체 본문은 `get_provision_detail`로 유도.

### 5.1 suggest_review_sources 키워드 입력 (0.2.0 minor — additive 입력/필드)

- 선택적 입력 `keywords: list[str] | None`: 호스트 LLM이 question에서 추출한 검색어 배열. 제공 시 서버 규칙 추출(`_extract_keywords`)보다 **우선 사용**, 생략·무효 시 규칙 추출 fallback. 정규화: 문자열만·공백 제외 2자 이상·순서 보존 dedupe·최대 10개. 클라이언트 키워드가 0건 + 오류 없음이면 규칙 추출로 보강.
- 응답 additive 필드: `keyword_source`(`client` | `fallback` | `client+fallback`). `extracted_keywords`는 **실제 검색에 사용된 키워드**를 반환(question-only 호출 시 기존 규칙 추출 결과와 동일).
- 기존 필드 삭제·이름변경 없음(순수 additive). 단 §5.2 candidates cap과 함께 0.2.0 minor에 포함 → contract_version **0.2.0**.

### 5.2 suggest_review_sources 출력 크기 상한 (0.2.0 minor — 기존 필드 거동 변경)

- 반환 `candidates`: 최대 **15건**(`_SUGGEST_CANDIDATES_MAX`). 선별 = 문서(rule_set) 단위 대표 후보 우선 확보(**매칭 문서 수가 15 이하면 각 문서 최소 1건 보장**; 초과 시 **관련도(매칭 키워드 수) 상위 문서 우선, 동률이면 위계 상위**, 탈락 문서는 `recommended_review_order`로 안내) + **관련도(매칭된 distinct 키워드 수) 우선** (v0.1.6; 동률이면 중요(앞쪽) 키워드·위계·provision_id tie-break). `recommended_review_order`·`total`은 **suggest 내부 candidate pool(cap 이전 전체) 기준** — 단 개별 `search_provision`은 키워드당 `_RESULTS_MAX`(30건)로 별도 truncate되므로, 그 상한을 넘는 매칭은 pool 진입 전 누락될 수 있음(즉 law.go.kr 전체 매칭의 완결성까지 보장하지는 않음). 반환 후보 **표시 순서**는 위계(hierarchy)·provision_id순 유지(`recommended_review_order`와 정합).
- 반환 후보 `snippet`: 최종 길이 **≤ 300자**(`_SUGGEST_SNIPPET_MAX`, 초과 시 말줄임표). 전체 본문은 `get_provision_detail`로 유도.
- 응답 additive 필드: `returned`(반환 후보 수), `truncated`(전체 > 반환 여부), `note`(truncated 시 추가 검색 안내). `total`은 cap 이전 전체 후보 수.
- 동기: MCP 단일 도구 응답 토큰 hard limit(25,000) 회피 및 경고 임계(10,000) 초과 가능성 완화(최악 응답 실측 ~12.7k chars로 hard limit은 하회하나 경고 임계는 입력에 따라 근접 가능). 기존 필드 삭제·이름변경은 없으나 `candidates`가 전체→상위 ≤15건으로 **거동이 변경**되어(§6 표 "응답 schema … 변경" = minor) 순수 additive로 보지 않음 → contract_version **0.2.0**(0.1.0 → 0.2.0). 0.x 대역이라 minor도 breaking 허용.

## 6. contract_version 관리

- 본 문서 contract_version: **0.2.0** (line 3 참조; 0.1.0 첫 publish → 0.2.0 minor)
- 코드 상수: `korean_rnd_regs_mcp.provision_id.CONTRACT_VERSION`
- 변경 정책 (0.x.x — unstable signal):

| 변경 종류 | semver bump | 예시 |
|---|---|---|
| patch | 0.1.x | 오류 메시지 문구 수정, 내부 endpoint URL 변경 (외부 영향 없음) |
| minor | 0.x.0 | provision_id 포맷 확장(가지조문 등), 응답 schema 추가·변경 (0.x.x 대역에서는 minor도 breaking change 허용) |
| major | 1.0.0 | API 안정화 선언 (semver 1.0+ 이후 SemVer 표준 적용) |

### 변경 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| 0.1.0 | 2026-05-24 | **첫 publish version**. 국가법령정보 OpenAPI 기반 13 rule set 지원 (Tier 1 혁신법 family 3개, Tier 2 핵심 행정규칙 4개, Supplementary 6개). 5 MCP tools + 1 MCP prompt(`review_regulation`), JO(조문)/BP(별표) provision_id, 표준 오류 코드 6종, 행정규칙 XML schema 2종 지원(표준 + 평면 fallback) |
| 0.2.0 | 2026-06-04 | **minor bump** (패키지 0.1.5와 함께). `suggest_review_sources` 개선 — (입력) 선택 `keywords` 배열 위임(생략 시 규칙추출 fallback), (응답 additive) `keyword_source`·`returned`·`truncated`·`note`, (거동 변경) `candidates`를 전체→위계·중요도 상위 ≤15건 cap + snippet ≤300자(§5.1·5.2). 기존 필드 삭제·이름변경 없음. `total`·`recommended_review_order`로 truncation 복구 안내 |
| 0.2.0 (유지) | 2026-06-05 | 패키지 **0.1.6** 검색 recall·관련도 개선. **contract_version bump 없음** — 응답 schema(필드·shape) 불변, `candidates` 표시 순서(위계순) 불변. 거동: `search_provision` 토큰 AND 매칭(다중 토큰 query 결과가 늘어나는 strict superset; 단일 토큰 불변), `candidates` cap 선별 기준을 관련도(매칭 키워드 수) 우선으로 변경(§5.2), suggest 내부 1-hop 동의어 union. 기존 필드·shape·표시 순서가 그대로라 호환 깨짐 없음 → 0.2.0 유지 |

- 도구 응답에 `contract_version` 필드 포함 권장 (search_provision·get_provision_detail·suggest_review_sources). 클라이언트가 호환 여부 확인 가능.
