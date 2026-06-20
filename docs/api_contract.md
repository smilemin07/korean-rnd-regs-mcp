# korean-rnd-regs-mcp API Contract

- contract_version: **0.6.0** (0.1.0 첫 publish → 0.2.0 → 0.3.0 → 0.4.0 → 0.5.0 → 0.6.0 minor bump, §6 변경 이력 참조)
- 작성일: 2026-05-24 (0.2.0 개정: 2026-06-04, 0.3.0 개정: 2026-06-07, 0.4.0 개정: 2026-06-09, 0.5.0 개정: 2026-06-10, 0.6.0 개정: 2026-06-13)
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
| `unit_id` (선택) | `JO` + 4자리 이상 숫자(조문, 예: `JO0003`) **또는** `BP` + 4자리 숫자(본별표, 예: `BP0001`=별표 1) **또는** `BP` + 6자리 숫자(가지별표 — 번호 4자리 + 가지 2자리, 예: `BP000102`=별표 1의2; 0.5.0) | 생략 시 document-level reference. BP 5자리 등 그 외 길이는 디코드 의미 미정의로 `invalid_provision_id` (0.5.0 협소화 — 종전 "4자리 이상"에서 변경, 서버 발급 이력은 4자리뿐이라 실영향 0) |

**JO vs BP**: LIVE 검증에서 일부 행정규칙(예: "국가연구개발사업 연구개발비 사용 기준" ID=2100000278740)은 조문 0개 + 별표 30개로 구성됨을 발견. 따라서 별표 단위 reference가 필요. `unit_type(unit_id)` 헬퍼로 article/annex/document 판정.

### 3.2 예시

```
law:260807                       # 국가연구개발혁신법(MST=260807, 2025-02-28 시행) 전체
law:260807:JO0003                # 동 법 제3조
admrul:2100000023234             # 행정규칙(ID=2100000023234) 전체
admrul:2100000023234:JO0007      # 동 행정규칙 제7조
admrul:2100000278740:BP0001      # "연구개발비 사용 기준" 별표 1 (기본사업연구개발비계상기준)
admrul:2100000278740:BP0030      # 동 행정규칙 별표 30
law:189938:BP000102              # 법령 별표 1의2 형식 (가지별표 인코딩 예시, 0.5.0)
```

### 3.3 doc_type 선행 강제 이유

- a (법령 상세) vs b (행정규칙 상세) **dispatch 라우팅 키**로 사용.
- doc_type 없이 ID만 받으면 어느 endpoint를 호출할지 결정 불가 → silent failure 또는 잘못된 endpoint 호출.

### 3.4 구현

- 모듈: `src/korean_rnd_regs_mcp/provision_id.py`
- 공개 API: `parse(str) -> ProvisionId`, `build(doc_type, doc_id, unit_id=None) -> str`, `unit_type(unit_id) -> str` (article/annex/document), `unit_label(unit_id) -> str` (제N조/별표 N/별표 N의M — 0.5.0 가지-aware), `ProvisionId` dataclass, `InvalidProvisionId` 예외, `CONTRACT_VERSION` 상수.
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
  "contract_version": "0.6.0",
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
| `annex_parse_failed` | 법령 별표 파싱 실패 (search_provision, 0.4.0) | fault-isolated — 조문 검색은 정상, errors에 rule_set_id와 함께 노출 |
| `annex_unavailable_parse_failed` | 별표 파싱 실패로 BP 상세조회 불가 (get_provision_detail, 0.4.0) | not_found 대신 정직하게 표면화 — 공식 원문 확인 안내 |
| `timeout` | search_provision fan-out 응답 시간 예산 초과로 해당 규정 조회 생략 (0.6.0) | graceful skip — `errors`에 rule_set_id와 함께 노출, 완료된 규정 결과는 정상 반환(부분 응답) |

### 4.3 보안 정책

- LawApiError.message는 `_request_with_retry`에서 type name만 사용하여 URL/query params (특히 `OC=<key>`)가 절대 포함되지 않음 (source layer 차단).
- main.py의 도구 응답 출력 직전 `_sanitize_error_message`가 LAW_API_KEY 값을 추가 redact (defense-in-depth).
- 도구 응답의 어느 필드에도 LAW_API_KEY 값·앞자리·hash 미포함.

## 5. 응답 길이 정책

- `search_provision`의 `snippet`: 각 결과당 **≤ 2000자**, 전체 응답 직렬화 **≤ 16,000자**(0.2.5 — 초과 시 뒤쪽 결과 절단·최소 1건 보장, 기존 `returned`/`truncated` 필드로 신호. 25개 규정 확대로 광역 질의 응답 40k+자 실측에 따른 예산 도입)
- `get_provision_detail` 본문: 조문(article)은 길이 제한 없음. 별표(annex)는 **size-tiered**(v0.4.0, §5.5) — 직렬화 응답이 보수 예산(`_ANNEX_DETAIL_CHAR_BUDGET`=16,000 chars)을 넘으면 본문 미수록(`content_format=oversized_pointer`) + 공식 링크 안내, 본문 없는 서식파일 별표는 `content_format=external_file_only`.
- 동기: Claude Code MCP는 도구 응답이 일정 크기 초과 시 경고·truncation 가능 — `search_provision`은 후보 제시용이므로 snippet으로만 노출하고 전체 본문은 `get_provision_detail`로 유도.

### 5.1 suggest_review_sources 키워드 입력 (0.2.0 minor — additive 입력/필드)

- 선택적 입력 `keywords: list[str] | None`: 호스트 LLM이 question에서 추출한 검색어 배열. 제공 시 서버 규칙 추출(`_extract_keywords`)보다 **우선 사용**, 생략·무효 시 규칙 추출 fallback. 정규화: 문자열만·공백 제외 2자 이상·순서 보존 dedupe·최대 10개. 클라이언트 키워드가 0건 + 오류 없음이면 규칙 추출로 보강.
- 응답 additive 필드: `keyword_source`(`client` | `fallback` | `client+fallback`). `extracted_keywords`는 **실제 검색에 사용된 키워드**를 반환(question-only 호출 시 기존 규칙 추출 결과와 동일).
- 기존 필드 삭제·이름변경 없음(순수 additive). 단 §5.2 candidates cap과 함께 0.2.0 minor에 포함 → contract_version **0.2.0**.

### 5.2 suggest_review_sources 출력 크기 상한 (0.2.0 minor — 기존 필드 거동 변경)

- 반환 `candidates`: 최대 **15건**(`_SUGGEST_CANDIDATES_MAX`). 선별 = 문서(rule_set) 단위 대표 후보 우선 확보(**매칭 문서 수가 15 이하면 각 문서 최소 1건 보장**; 초과 시 **제목 매칭 수(title_hits) 상위 문서 우선, 동률이면 관련도·위계 상위**, 탈락 문서는 `recommended_review_order`로 안내) + **제목 매칭 수(title_hits) 우선** (v0.1.7; 동률이면 관련도(매칭 distinct 키워드 수)·위계·provision_id tie-break. v0.1.6의 매칭수-우선 및 키워드순서 priority는 제거 — 일반어 다수 매칭 무관 조문이 제목 직매칭 핵심 조문을 매몰시키던 문제 해소). `recommended_review_order`·`total`은 **suggest 내부 candidate pool(cap 이전 전체) 기준** — 단 개별 `search_provision`은 키워드당 `_RESULTS_MAX`(30건)로 별도 truncate되므로, 그 상한을 넘는 매칭은 pool 진입 전 누락될 수 있음(즉 law.go.kr 전체 매칭의 완결성까지 보장하지는 않음). 반환 후보 **표시 순서**는 위계(hierarchy)·provision_id순 유지(`recommended_review_order`와 정합).
- 반환 후보 `snippet`: 최종 길이 **≤ 300자**(`_SUGGEST_SNIPPET_MAX`, 초과 시 말줄임표). 전체 본문은 `get_provision_detail`로 유도.
- 응답 additive 필드: `returned`(반환 후보 수), `truncated`(전체 > 반환 여부), `note`(선택적 안내문 — truncation 추가검색 안내 및/또는 `keyword_source=="fallback"` 시 품질 저하 경고. v0.1.7부터 두 사유가 함께 표시될 수 있음). `total`은 cap 이전 전체 후보 수.
- 동기: MCP 단일 도구 응답 토큰 hard limit(25,000) 회피 및 경고 임계(10,000) 초과 가능성 완화(최악 응답 실측 ~12.7k chars로 hard limit은 하회하나 경고 임계는 입력에 따라 근접 가능). 기존 필드 삭제·이름변경은 없으나 `candidates`가 전체→상위 ≤15건으로 **거동이 변경**되어(§6 표 "응답 schema … 변경" = minor) 순수 additive로 보지 않음 → contract_version **0.2.0**(0.1.0 → 0.2.0). 0.x 대역이라 minor도 breaking 허용.

### 5.3 suggest_review_sources overflow_candidates (0.3.0 minor — 응답 additive 필드)

- 신규 최상위 필드 **`overflow_candidates`**: cap(`_SUGGEST_CANDIDATES_MAX`=15)에 들지 못한 후보 조문을 노출(호스트의 drill-down 용). 각 항목은 `{ "provision_id": str, "label": str }`만 포함(snippet 없음). `label` 형식 예: `"국가연구개발사업 연구개발비 사용 기준 제74조(사전 승인 절차)"`(문서명 + `provision_id.unit_label` + 조문제목). 호스트는 그 `provision_id`로 `get_provision_detail`을 호출해 본문 확인.
- 정렬: `candidates` cap 선별과 **동일 relevance 기준**(`_relevance_key`: 제목매칭 수 → 매칭 distinct 키워드 수 → 위계 → provision_id). `candidates`와 항상 disjoint.
- 상한: 최대 **`_OVERFLOW_CANDIDATES_MAX`=30건**, 그리고 overflow 추가는 **전체 응답 직렬화가 `_SUGGEST_RESPONSE_CHAR_BUDGET`=16,000 chars를 넘지 않는 선에서만**(base 응답을 먼저 확정한 뒤 잔여 예산으로 채우며, base 자체가 16k를 초과하면 overflow는 비움). 두 상한 중 먼저 걸리는 쪽에서 중단. 즉 16k는 **overflow 추가분에 대한 상한**이며, 비정상적으로 큰 `question` 입력 등으로 base가 단독으로 큰 경우의 전체 응답 크기까지 16k로 보장하지는 않음(이 경우 v0.1.7과 동일하게 base만 반환 — v0.1.8이 신규 outage 위험을 더하지 않음).
- 신규 최상위 필드 **`overflow_truncated`**(bool): cap/예산으로 overflow 일부라도 누락 시 `true`. overflow가 없으면 `overflow_candidates`는 `[]`·`overflow_truncated`는 `false`(두 필드는 항상 포함).
- 기존 필드(`candidates`·`total`·`returned`·`truncated`·`recommended_review_order`·`note`) 삭제·이름변경·shape 변경 없음(순수 additive). `truncated`(candidates cap 여부)와 `overflow_truncated`(overflow index 추가 누락 여부)는 서로 다른 의미.
- 동기: Andy 명시 가치("cap에 가려진 조항까지 보고 drill-down")를 직접 충족하되, 응답 크기 증가로 인한 클라이언트 truncation을 16k char 보수 예산 + 라이브 4경로 스모크로 차단. 응답 schema에 필드 추가 → contract_version **0.3.0**(0.2.0 → 0.3.0).

### 5.4 suggest_review_sources degraded note 강화 (0.3.0 유지 — `note` 텍스트 변경)

- `note`(기존 선택 필드)의 **문구만** 변경 — 신규 필드·shape 변경 없음 → contract_version **0.3.0 유지**.
- `keyword_source`가 `fallback`·`client+fallback`이거나 무키워드 early-return(후보 0건)인 경우, `note`에 **`[degraded]` 마커 + 명령형 재호출 지시**(법령 절차·개념어를 추론해 `keywords`로 `suggest_review_sources` 재호출)를 부착. 기존 약한 권고("정확도를 높이려면 keywords를 전달하십시오")를 대체.
- 적용 경로 확대: 기존에는 `keyword_source=="fallback"`에만 note가 붙었으나, v0.1.9부터 `client+fallback`·early-return 경로에도 부착(이전 누락 보강).
- **M2 soft-gate**: degraded여도 `candidates`는 보류 없이 그대로 반환(호스트가 무시해도 빈손이 되지 않음). gate는 신호일 뿐 결과를 막지 않으므로 재호출 루프·outage 위험 없음.
- 동기: 검토 품질이 `keyword_source` 품질에 좌우됨(라이브 eval 확인). `keywords` arg description·`review_regulation` 프롬프트의 위임 지시(필수화 + degraded 시 재호출)와 정합. 관련 조문 추출 알고리즘(v0.1.7)·fallback 추출기 불변.

### 5.5 get_provision_detail 법령 별표 지원 (0.4.0 minor — 응답 additive 필드 + 거동)

- 법령(law, 시행령) 별표(BP)를 `get_provision_detail`·`search_provision`에서 지원(이전: 행정규칙 별표만). `get_law_detail`이 `<별표단위>`를 파싱(**fault-isolated** — 별표 파싱 실패가 조문 반환을 깨지 않고 `annex_parse_error`로 표면화). manifest `innovation_decree.unit_types`를 `article`→`both`로.
- **size-tiered get_provision_detail(annex)**: 직렬화 응답이 `_ANNEX_DETAIL_CHAR_BUDGET`=16,000 chars 이내면 본문 전문(`content_format=plain_text_verbatim`); 초과하면 본문 미수록 + 신규 필드 `content_available=false`·`content_format=oversized_pointer`·`is_complete=false`·`omitted_reason`·`omitted_char_count`·`required_action`·`verbatim_quote_allowed=false`. 본문 없는 서식파일 별표는 `content_format=external_file_only`. 삭제된 별표는 `annex_status=deleted_stub`.
- **정확성 가드**: `content_format`이 `plain_text_verbatim`이 아니면 그 `content`는 규정 원문이 아니라 안내 텍스트 — 호스트는 인용 금지(`verbatim_quote_allowed=false`), `attached_file_url`/`document_source_url` 공식 원문 확인. `review_regulation` 프롬프트·README 임베드 사본에 동일 규칙 명문화.
- **search_provision 별표 스니펫**: 공백 정렬 표의 행 중간 절단을 막기 위해 개행(줄) 경계로 자르고, 질의 전 토큰의 매칭 줄을 합집합 멀티윈도우로 발췌(0.2.3 — cap 6·±1줄 맥락·비연속 구간 "…" 구분·≤2000자 불변; 0.2.4 — 토큰별 ceil(cap/토큰수) quota 선확보로 빈출 토큰의 cap 선점 기아 방지). 본문 전체 수록/부분 발췌에 따라 마커 2형 부착(전체 수록 시 "발췌" 미표기). 별표 파싱 실패는 `errors`에 `code=annex_parse_failed`로 노출.
- 한도값 근거: MCP 응답 토큰 hard limit(Claude Code 25,000) 회피용 보수 char proxy. 웹/Desktop은 더 클 수 있으나(약 150k chars 단서) ChatGPT 한도 확인 불가 → 4경로 최저선 보수 적용. LIVE 4경로 실측(별표2·7) 통과 후 상향은 별도 최적화로 분리.
- 기존 필드 삭제·이름변경 없음(additive). 응답 schema에 신규 필드 추가 + 거동(법령 별표 노출) → contract_version **0.4.0**(0.3.0 → 0.4.0).

### 5.6 별표 발견성·정확 선택 강화 (0.5.0 minor — 응답 additive 필드 + BP 인코딩 확장 + 거동)

- **document-level `annexes` 목록** (additive): `get_provision_detail`(unit_id 생략) 응답에 별표 목록 `annexes: [{provision_id, label, title, dependent_article_hints?, deleted?}]` 추가 — 호스트가 별표 번호를 추측하지 않고 제목을 보고 BP를 선택. **`별표구분`=='별표'인 항목만** 수록(별지·서식 제외 — 아래 거동 변경 참조), 본문 미포함(제목만). `annexes_count`는 종전 의미(별표단위 전건 — 별표·별지·서식 포함) 유지(하위호환), 전건 구성은 신규 `annexes_count_by_kind`(예: `{"별표": 8, "별지": 22}`)로 표시 — count(30)와 목록 길이(8)의 차이를 응답 내 산술로 해소.
- **가지별표 BP 인코딩** (0.5.0): OpenAPI `별표단위`의 `별표가지번호` 파싱 추가. 가지 00(본별표)은 종전 4자리 `BP{번호4}` **불변**, 가지 != 00은 6자리 `BP{번호4}{가지2}`(예: `BP000102`=별표 1의2). `_UNIT_PATTERN`을 BP 4/6자리 한정으로 **협소화**(5자리 등은 `invalid_provision_id` — 종전 "4자리 이상" 대비 형식적 변경이나 서버 발급 이력은 4자리뿐). `unit_label` 가지-aware("별표 1의2").
- **별지·서식 BP 노출 제외** (거동 변경 = 오도달 버그 수정): `별표구분`이 '별지'·'서식'인 항목은 별표와 번호가 독립 채번이라 BP id가 충돌(별표1·별지1 모두 BP0001) — 종전에는 별지가 검색에 노출되고 조회 시 동번호 별표가 반환되는 **오도달 결함**. 0.5.0부터 search_provision·get_provision_detail(BP)·document-level 목록에서 별지·서식 제외. 별지·서식만 매칭되던 질의는 결과가 줄거나 0건일 수 있음(공식 원문은 `document_source_url`).
- **(번호,가지) 엄격 매칭** (거동 변경): get_provision_detail(BP)이 종전 문서순 첫 일치에서 (번호, 가지) 정확 일치로 변경 — 해당 별표가 없으면 `not_found`(우연 반환 제거).
- **`dependent_article_hints`** (additive): 별표 상세·document-level 목록 항목에 별표 제목의 조문 참조(예: "(제19조제3항 관련)")를 전건 추출한 문자열 list. **제목 기반 미검증 단서** — provision_id로 변환하지 않으며, 호스트는 힌트 자체를 인용하지 말고 해당 조문을 직접 조회해야 함(`dependent_article_hints_note` 동봉, 프롬프트 5단계에 동반조회 1-hop 지시).
- **별표 파싱 실패 정직성** (additive, law 한정): law 별표 파싱 실패 시 document-level에 `annexes_unavailable: true`·`annex_parse_error` 표면화 — `annexes_count=0`이 "별표 없음"으로 오인되는 거짓 신호 차단. admrul 경로에는 fault-isolation이 없어 본 플래그가 발화하지 않음(law 전용).
- **별표 제목 정규화**: 소스가 CDATA 안에 사전 이스케이프 텍스트를 송신하는 경우(삭제 별표 제목 '삭제 &lt;날짜&gt;')를 live_api 파서 단일 관문에서 `html.unescape` — 응답 전 경로(검색·상세·목록)의 제목 표기 일원화. 삭제 별표는 제목 기반 판정(`'삭제'` 정확 일치 또는 `'삭제 <'` 시작)으로 목록 `deleted: true` + 상세 `annex_status=deleted_stub` 정합.
- 동기: v0.2.0 첫 실사용에서 호스트가 라벨 없는 `annexes_count` 정수만 보고 별표를 추측 선택(운으로 적중)한 갭과, 가지별표(공익신고자 보호법 시행령 별표 1의2 등)가 주소 자체가 없어 도달 불가하던 결함을 함께 해소. 응답 schema 신규 필드 + BP 인코딩 확장 + 오도달 버그 수정 거동 변경 → contract_version **0.5.0**(0.4.0 → 0.5.0).

### 5.7 소관부처(ministry) resolve 필터 + list_rule_sets 노출 (0.6.0 minor — 응답 additive 필드 + resolve 거동)

- **`list_rule_sets` 응답에 `ministry` 필드 추가** (additive): 각 rule set 항목에 `ministry`(소관부처명 문자열 또는 `null`) 추가. 기존 필드 삭제·이름변경 없음 — 순수 additive이나 응답 schema에 신규 키가 추가되므로 minor bump.
- **소관부처 resolve 필터** (거동 변경, opt-in): `RuleSet`에 `ministry`(Optional, manifest yaml 필드) 추가. `ministry`가 지정된 rule set은 `resolve_latest_doc_id`가 검색 행의 `소관부처명`을 콤마 분리·**정확일치**로 비교하여 자부처 행만 채택(substring 매칭 금지). 동명 규정이 복수 부처에 실재할 때(예: "기술료 징수 및 관리에 관한 통합요령"이 산업통상부·기후에너지환경부 양건 현행) 타부처 건으로 오집되던 결함 해소. 일치 행이 없으면 manifest fallback(가용성 유지). `ministry` 미기재 rule set(기존 다수)은 거동 불변. 캐시 키는 `("resolve", api_target, title, ministry or "")`로 확장.
- **별표 외 부속문서 안내 일반화** (거동 — `warnings` 텍스트): document-level `warnings`의 "본문 조회 불가" 안내를 별지·서식 하드코딩에서 비'별표' 전 종류(별첨·붙임 포함)로 일반화 — 신종 `별표구분`이 안내 없이 누락되던 갭 해소(필드 무변).
- 동기: 지원 규정 확대(과기정통부 family 9건)에 동명 2부처 규정(기술료 통합요령)이 포함되어 부처 미지정 resolve가 타부처 현행본을 반환하는 것을 LIVE 실증 — 소관부처 필터로 차단. 응답 schema 신규 필드(`list_rule_sets.ministry`) → contract_version **0.6.0**(0.5.0 → 0.6.0). 규정 데이터 추가·삭제(28개로 재편)는 계약 외 corpus 변경.

## 6. contract_version 관리

- 본 문서 contract_version: **0.6.0** (line 3 참조; 0.1.0 첫 publish → 0.2.0 → 0.3.0 → 0.4.0 → 0.5.0 → 0.6.0 minor)
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
| 0.2.0 (유지) | 2026-06-06 | 패키지 **0.1.7** 검색 랭킹 정상화 + 호스트 위임 강화. **contract_version bump 없음** — 응답 schema·필드·shape·표시 순서(위계순) 불변. 거동: `candidates` cap 선별 1차 기준을 제목 매칭 수(title_hits) 우선으로 변경하고 v0.1.6 `_priority`(키워드 순서) 제거(§5.2). `keywords` description·프롬프트로 호스트 위임 강화, `keyword_source=="fallback"` 시 기존 `note` 필드에 품질 경고 병기(필드 추가 없음). 기존 필드·shape 불변 → 0.2.0 유지 |
| 0.3.0 | 2026-06-07 | **minor bump** (패키지 0.1.8). `suggest_review_sources` 응답에 **`overflow_candidates`**(cap 밖 조문을 `{provision_id, label}`로 relevance 순 노출, ≤30건·overflow 추가는 전체 응답이 16k char를 넘지 않는 선에서만) + **`overflow_truncated`**(bool) **신규 필드 추가**(§5.3). 호스트가 cap에 가려진 조문을 보고 `get_provision_detail`로 drill-down. 기존 필드 삭제·이름변경·shape·거동 변경 없음(순수 additive)이나 응답 schema 추가이므로 minor bump. `review_regulation` 프롬프트·서버 `note`·도구 docstring에 새 필드 활용 안내 동기화 |
| 0.3.0 (유지) | 2026-06-07 | 패키지 **0.1.9** 키워드 위임 강제 신호. **contract_version bump 없음** — 응답 schema·필드·shape 불변(`note` 텍스트 변경 + `keywords` description·`review_regulation` 프롬프트 텍스트만). `note`를 `fallback`·`client+fallback`·무키워드 early-return 세 경로에 **`[degraded]` 마커 + 명령형 재호출 지시**로 강화(§5.4), `candidates`는 보류 없이 반환(M2 soft-gate). 관련 조문 추출 알고리즘(v0.1.7)·fallback 추출기 불변 → 0.3.0 유지 |
| 0.3.0 (유지) | 2026-06-08 | 패키지 **0.1.10** 절차 흐름 시각화. **contract_version bump 없음** — 응답 schema·필드·shape·검색/랭킹/fallback 불변. `review_regulation` 프롬프트(`_REVIEW_PROMPT_TEMPLATE`) 출력 형식에 조건부 8절 "절차 흐름" 추가(프롬프트 텍스트만, 도구 응답 무관). README 임베드 사본 동기화 → 0.3.0 유지 |
| 0.4.0 | 2026-06-09 | **minor bump** (패키지 **0.2.0**). 법령(시행령) 별표 지원 — `get_law_detail` 별표 파싱(fault-isolated, `annex_parse_error`), `innovation_decree.unit_types` `article`→`both`, `search_provision`/`get_provision_detail`에서 혁신법 시행령 별표 1~7 노출(§5.5). `get_provision_detail(annex)` **size-tiered**: 신규 필드 `content_format`·`content_available`·`verbatim_quote_allowed`·`is_complete`·`omitted_reason`·`omitted_char_count`·`required_action`·`annex_status` 추가, 대용량 별표(별표2·7)는 본문 미수록 포인터, 서식파일 별표는 external_file_only. 별표 스니펫 줄단위 절단. `review_regulation` 프롬프트·README 임베드 사본·manifest known_limitations 동기화(별표 미지원 문구 정정). 기존 필드 삭제·이름변경 없음(additive) → minor bump |
| 0.5.0 | 2026-06-10 | **minor bump** (패키지 **0.2.1**). 별표 발견성·정확 선택 강화(§5.6) — document-level `annexes` 목록·`annexes_count_by_kind`·`annexes_unavailable`·`dependent_article_hints`(+note) additive 추가; BP 6자리 가지별표 인코딩(`BP{번호4}{가지2}`) + `_UNIT_PATTERN` 4/6자리 협소화; **별지·서식 BP 노출 제외**(별표↔별지 번호 충돌로 인한 오도달 버그 수정, 별지만 매칭되던 검색은 결과 감소 가능); get_provision_detail(BP) (번호,가지) 엄격 매칭(우연 첫-일치 제거); 별표 제목 unescape(단일 관문)·제목 기반 deleted 판정; suggest 단방향 현장어 alias(응답 schema 무관); `review_regulation` 프롬프트 5단계에 의존조문 동반조회(1-hop)·문서레벨 목록 선택 지시 + README 동기화 |
| 0.5.0 (유지) | 2026-06-11 | 패키지 **0.2.2** 별표 발견성 마감(호스트 오도·막다른 길 신호 제거). **contract_version bump 없음** — 응답 schema·필드·shape·검색/랭킹/fallback 알고리즘 불변(기존 `warnings`·오류 `message` 텍스트 + `review_regulation` 프롬프트 텍스트만). 별지·서식 보유 문서의 document-level `warnings`에 본문 조회 불가·공식 원문 안내 1줄, `dependent_article_hints` 미검증 경고 1줄; BP `not_found` message에 document-level `annexes` 목록 재조회 복구 안내; `auth_failed` message에 HTTP(`?oc=`) 키 전달 확인 병기; 프롬프트 degraded 재호출 종료조건(최대 1회) + README 동기화; manifest known_limitations stale 문구 정정(v0.2.0~0.2.1 별표 지원 미반영분). Dockerfile fastmcp==3.4.2 핀(빌드 재현성 — 계약 외) → 0.5.0 유지 |
| 0.5.0 (유지) | 2026-06-12 | 패키지 **0.2.3** 대용량 별표 핀포인트 도달성 복구. **contract_version bump 없음** — 응답 schema·필드·shape·검색/랭킹/fallback 알고리즘 불변. 거동: `search_provision` 별표 스니펫(`_annex_snippet`)을 anchor 단일 매칭 줄 발췌 → 질의 전 토큰 매칭 줄 합집합 멀티윈도우(cap 6·±1줄 맥락·윈도우 병합·"…" 구분·예산 내 라운드로빈 확장)로 개편(§5.5 갱신), 마커 2형 분기(전체 수록/부분 발췌). snippet ≤2000자(`_SNIPPET_MAX`) 불변. `oversized_pointer`의 `content`·`required_action` 문구에 document_source_url 1순위·첨부 HWP/HWPX 형식 보수 안내(텍스트만, 필드 무변) → 0.5.0 유지 |
| 0.5.0 (유지) | 2026-06-12 | 패키지 **0.2.4** 검증 후속 보정. **contract_version bump 없음** — 응답 schema·필드·shape 불변. 거동: 별표 스니펫 매칭 줄 수집에 토큰별 quota(ceil(cap/토큰수)) 도입(§5.5 갱신 — 빈출 토큰 cap 선점 기아 방지, 단일 토큰 불변). manifest 데이터: 혁신법 family 3건 현행화(283849·286879·시행일 2026-06-11 — 2026-06-11 시행 개정 발효 반영, 계약 외 데이터) → 0.5.0 유지 |
| 0.5.0 (유지) | 2026-06-13 | 패키지 **0.2.5** 지원 규정 확대 1차(3부처 R&D, 17→25개 — 산업기술혁신 촉진법 family 4건·중소기업 기술혁신 촉진법 family 4건, 계약 외 데이터) + `search_provision` 전체 응답 직렬화 예산 16k char 도입(§2 갱신 — 초과 시 뒤쪽 결과 절단·최소 1건 보장, 기존 `returned`/`truncated` 필드 신호·schema 무변). **contract_version bump 없음** → 0.5.0 유지 |
| 0.6.0 | 2026-06-13 | **minor bump** (패키지 **0.2.6**). 지원 규정 재편 2차(25→28개 — 과기정통부 family 9건 추가·보조 법령 6건 제거, 계약 외 corpus). 소관부처 resolve 필터(§5.7 — `RuleSet.ministry` + 검색 행 소관부처명 콤마·정확일치, 동명 2부처 오집 차단·캐시 키 ministry 확장); `list_rule_sets` 응답에 `ministry` 필드 additive 추가(bump 근거); 별표 외 부속문서 안내 별첨·붙임 일반화(`warnings` 텍스트); search_provision fan-out 응답 시간 예산(20s) 가드 + 신규 오류코드 `timeout`(graceful skip·§4.2). 검색/랭킹/fallback 알고리즘 불변 → 0.5.0 → 0.6.0 |
| 0.6.0 (유지) | 2026-06-14 | 패키지 **0.2.7** 구동 안정성 강화(외부 API 대기 상한 보수화). **contract_version bump 없음** — 응답 schema·필드·shape·오류코드·검색/랭킹/fallback 알고리즘 불변. 거동(요청 경로 한정): live_api 외부 OpenAPI 요청 timeout 정수 30s → `(connect 8s, read 12s)` 튜플 + `max_retries` 3→2(worst-case 스레드 점유 ~186s→82s 보수화, 부등식 read 12 < `_FANOUT_BUDGET_S` 20 < 커넥터). `timeout`(graceful skip) 오류 `message` 텍스트만 '부분 결과·재검색' 신호로 정제(code 불변). `_FANOUT_BUDGET_S`=20s 유지. 서버 부팅·HTTP transport 비의존 → 0.6.0 유지 |
| 0.6.0 (유지) | 2026-06-17 | 패키지 **0.2.8** 검색 결과 관련도 정렬(광역 질의 매몰 방지). **contract_version bump 없음** — 응답 schema·필드·shape·오류코드 불변. 거동(요청 경로 한정): `search_provision`이 `_RESULTS_MAX`·16k 예산 절단 *직전*에 결과를 결정적 관련도 정렬키(문서 제목 적중 → 단위 제목 적중 → 본문 적중 → 단위유형 → 위계 → 기존 append 순서)로 재정렬 — 광역 질의에서 문서 제목이 직접 일치하는 후순위 규정(예: '연구개발비'→「연구개발비 사용 기준」)이 앞순위 규정에 예산을 빼앗겨 절단되던 결함(v0.2.7 LIVE eval) 해소. 정렬키·점수는 응답 미노출(신규 필드 0), 검색 토큰 매칭·fallback·fan-out 예산·`timeout` 불변. 검색 결과 표시 순서는 계약 보장 항목이 아님(선례 0.1.6·0.1.7 검색 거동 변경도 bump 없음). 서버 부팅·HTTP transport 비의존 → 0.6.0 유지 |
| 0.6.0 (유지) | 2026-06-17 | 패키지 **0.2.9** 규정 질의 도구 호출 유도(메타데이터 가드). **contract_version bump 없음** — 응답 schema·필드·shape·오류코드·검색/랭킹/fallback 알고리즘 불변. 거동: 메타데이터(텍스트)만 — FastMCP 서버 레벨 `instructions` 신설(MCP initialize 응답 payload에 호출 유도/금지 안내) + `search_provision`·`suggest_review_sources`·`get_provision_detail` docstring 첫 문단에 "사용 시점/호출 금지" 스탠자 prepend(기존 docstring 본문 보존). 호스트가 본 서버 범위 규정 질의에 일반지식 대신 도구를 먼저 호출하도록 유도하고 과호출(범위 밖·단순 대화)을 차단. 도구 입력 파라미터·응답 스키마 무변. 단 서버 `instructions`는 initialize payload 변경이라 배포 전 부팅 스모크 필수. 도구 호출 여부는 호스트 의존(Level B 비결정·자동 게이트 불가) → 0.6.0 유지 |
| 0.6.0 (유지) | 2026-06-18 | 패키지 **0.2.10** 검색 fan-out 지연 관측성(B1 — 스태빌리티 트랙 1단계). **contract_version bump 없음** — 응답 schema·필드·shape·오류코드·검색/랭킹/fallback 알고리즘·동시성 모델(`asyncio.to_thread` 기본 executor) 불변. 거동 변경 없음 — **서버 측 로그(stderr)만 additive 추가**: `search_provision` fan-out 요약(`event=search_fanout_summary`, INFO·wall_ms/done/skipped/max_rule_ms/slow_rule_count/errors_count) + 규정별 지연(`event=fanout_rule`, DEBUG) + `suggest_review_sources` 요약(`event=suggest_search_summary`, INFO·search_calls 등). 목적: 차기 B2(전용 bounded executor) 풀 크기 N 산정용 데이터. 신규 로그는 OC 키·요청 URL·query·keywords·예외 message 미포함(보안 회귀 테스트). 도구 응답에 신규 필드 0(로그는 서버 측만) → 0.6.0 유지 |
| 0.6.0 (유지) | 2026-06-19 | 패키지 **0.2.11** HTTP 멀티테넌트 키 보호 + MCP Registry 등록 마커. **contract_version bump 없음** — 응답 schema·필드·shape·검색/랭킹/fallback 알고리즘·외부 URL 불변. 거동(HTTP transport 한정): `--http` 요청에 `?oc=` 키가 없으면 기존 server env 키 silent fallback 대신 **기존 오류코드 `auth_failed`**(§4) 반환 — `_is_http_request` contextvar로 transport 구분, stdio(env 키 정상 경로)는 불변(무회귀). 신규 응답 필드·오류코드 0(`auth_failed`는 §4 기존). 부수: uvicorn `access_log=False`로 access log의 `?oc=` 키 기록 차단(transport·계약 외)·README `mcp-name` 마커·repo 루트 `server.json`(계약 외). 응답 계약 무변 → 0.6.0 유지 |
| 0.6.0 (유지) | 2026-06-20 | 패키지 **0.2.12** 도구 미가용 시 fail-closed 안내 + 범위 외 정직성. **contract_version bump 없음** — 응답 schema·필드·shape·오류코드·검색/랭킹/fallback·transport 불변. 서버 `_SERVER_INSTRUCTIONS`(initialize 메타데이터)에 fail-closed 분기(도구 미가용 시 훈련지식 단정 금지·새 대화/stdio 안내)+범위 외 정직성(`도구 호출 결과` 28개 밖이면 일반지식 명시·1차 출처) 2문장 append(기존 도구 호출 유도 구절 보존)·README "안정적으로 사용하기" 안내 섹션. 동기=v0.2.11 배포 후 라이브 eval에서 host-side 도구 미로드 시 훈련지식 단정(컴플라이언스 위험) 확인 — 호스트 로딩은 서버가 강제 불가라 피해완화. 도구 응답·계약 무변 → 0.6.0 유지 |
| 0.6.0 (유지) | 2026-06-20 | 패키지 **0.3.0** 보건복지부 R&D 규정 지원(28→32, 계약 외 corpus) + 미지원 규정 현행성 정직 가드. **contract_version bump 없음** — 응답 schema·필드·shape·오류코드·검색/랭킹/fallback·transport 불변. (데이터) `rule_sets.yaml`에 보건의료기술 R&D family 4건 추가(보건의료기술 진흥법 279703·시행령 282961·시행규칙 264101·운영·관리규정 admrul 2100000233560, 전건 표준 schema·ministry=보건복지부; 운영규정 표준협약서는 별지라 BP·검색 미노출). (프롬프트·텍스트) `_SERVER_INSTRUCTIONS` 범위 외 정직성 절 교체 — 미지원 규정의 고시번호·시행일·조문 번호·금액·비율·기한 등 변동 구체값 현행 단정 자제·1차 출처 안내; `review_regulation` 템플릿·prompt/플러그인 description에 보건의료 family 반영; 지원 카운트 28→32. 도구 응답·계약 무변 → 0.6.0 유지 |
| 0.6.0 (유지) | 2026-06-20 | 패키지 **0.4.0** 질병관리청 R&D 규정 지원 확대(32→36, 계약 외 corpus). **contract_version bump 없음** — 응답 schema·필드·shape·오류코드·검색/랭킹/fallback·transport·외부 URL 불변. (데이터) `rule_sets.yaml`에 질병관리청 R&D family 4건 추가(연구개발 관리 규정 2100000279440·전문기관 지정 고시 2100000277984·시설·장비 관리 규정 2100000214227·범부처 이어달리기 공통운영 지침 2100000197858, 전건 admrul·평면 schema·별표 0·ministry=질병관리청; 이어달리기는 19개 부처별 사본 중 질병관리청 사본을 부처 접두 제목으로 등록해 resolve 정확성 확보). (코드 상수) 검색 캐시 maxsize 50→64(확대 선제 마진, 동시성 모델·응답 불변). (텍스트) review_regulation 템플릿·description·지원 카운트 32→36. 도구 응답·계약 무변 → 0.6.0 유지 |

- 도구 응답에 `contract_version` 필드 포함 권장 (search_provision·get_provision_detail·suggest_review_sources). 클라이언트가 호환 여부 확인 가능.
