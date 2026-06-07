# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 형식을 따릅니다.
버전 번호는 [Semantic Versioning](https://semver.org/lang/ko/) 2.0.0을 따르되, 0.x.x 대역은 unstable signal이며 minor bump도 breaking change 허용입니다.

## [0.1.10] - 2026-06-08

`review_regulation` 프롬프트 출력 형식에 조건부 **8절 "절차 흐름"** 추가 — 검토 결과가 단계적 절차·조건 분기를 포함하면, 모든 MCP 클라이언트에서 렌더되는 텍스트 흐름(번호 단계+화살표, 단계별 근거 조문 병기)을 답변에 포함하도록 유도. `contract_version` **0.3.0 유지**(프롬프트 텍스트만 — 응답 schema·필드·검색/랭킹/fallback 알고리즘 불변). 변경은 `_REVIEW_PROMPT_TEMPLATE`와 README 임베드 사본 동기화에 한정 — 부팅·transport·health·캐시·도구 응답 비의존(outage 무위험). 설계는 `/disc` 3-AI 적대검증 수렴: 조건부 8절 신설 채택(7절 통합 기각 — 흐름은 의미상 독립 산출물이고 4·7절 확정 후 시각화해야 fabrication 위험↓), mermaid 미언급·텍스트 흐름만(미렌더 커넥터의 raw 노출 방지), 단계별 근거 조문 강제 + 규정에 없는 단계 임의 추가 금지(fabrication 가드). literal triple-backtick은 템플릿에 미포함(README 단일 코드펜스·동기화 테스트 보호).

### Added

- `== 최종 출력 형식 ==`에 조건부 `### 8. 절차 흐름` 절: 둘 이상의 시간순 단계 또는 [예]/[아니오] 조건 분기를 포함할 때만 작성(단순 정의·단일 조항·단일 가부 판단이면 절 전체 생략). 헤더를 "1~7절 제목·순서 고정, 8절은 조건부"로 명문화. 흐름은 언어 지정 없는 Markdown 코드블록의 번호+화살표(→), 각 단계 근거 규정명·조문번호 병기·4·7절 일치, 규정 외 일반 실무 단계(접수·검토·결재·통보) 임의 추가 금지·선후 불명 시 "추가 확인 필요".

### Changed

- README 임베드 프롬프트 사본을 `_REVIEW_PROMPT_TEMPLATE`와 동기화.

### Tests

- `test_review_regulation_prompt_includes_procedure_flow_section` 추가(8절·fabrication 가드·mermaid 미언급·literal 백틱3개 부재). 전체 156.

## [0.1.9] - 2026-06-07

`suggest_review_sources`의 fallback 안내(`note`)를 **명령형 degraded 신호**로 강화하고, 호스트 위임(`keywords` description·`review_regulation` 프롬프트)을 정합 강화. `contract_version` **0.3.0 유지**(응답 schema·필드 불변 — `note` 텍스트 변경 + description/prompt 텍스트만). 변경은 도구 응답 텍스트·도구 등록 description·프롬프트에 한정 — 부팅·transport·health·캐시 비의존. 목적: 검토 결과 품질이 `keyword_source` 품질에 크게 좌우되는 문제(라이브 eval로 확인 — 유능한 Claude 하니스는 현행 description만으로 첫 호출 keyword 위임 ~100%이나, 실패는 호스트 하니스 차이에 집중)에서, 서버가 keywords를 받지 못해 표면추출로 대체(degraded)한 경우 호스트가 법령 절차·개념어를 추론해 keywords로 **재호출**하도록 강하게 유도. 관련 조문 추출 알고리즘(v0.1.7)·fallback 추출기는 **불변**. 설계는 `/disc` 3-AI 적대검증 수렴: M2 soft-gate 채택(결과 보류하는 M3·required-param M4·서버→AI sampling 콜백은 기각 — 콜백은 주력 클라이언트(Claude.ai 웹 커넥터·ChatGPT 등) 미지원으로 outage 위험).

### Changed — degraded note 명령형화 (#1, M2 soft-gate)

- `suggest_review_sources`의 `note`: `keyword_source=="fallback"`·`"client+fallback"`·무키워드 early-return **세 경로 모두**에 명령형 재호출 지시 + **`[degraded]` 마커** 부착(기존 "정확도를 높이려면 keywords를 전달하십시오" 약한 권고를 교체). 신규 모듈 상수 `_RECALL_DIRECTIVE`·`_DEGRADED_NOTE_FALLBACK`·`_DEGRADED_NOTE_EMPTY`·`_DEGRADED_NOTE_CLIENT_FB`.
- **결과(`candidates`)는 그대로 반환**(보류 없음) — M2 soft-gate. degraded여도 빈손 없음 → outage·UX 회귀·재호출 루프 위험 0. 루프 invariant: gate는 `keyword_source`가 fallback/client+fallback일 때만 신호이며 결과를 막지 않으므로, 무효 keywords 재호출에도 최대 1회 의미있는 추가 왕복으로 종료.
- 기존 누락 보강: note가 없던 `client+fallback`·early-return 경로에 note 부착.

### Changed — 호스트 위임 정합 (#3)

- `keywords` arg description에 "규정 검토 질문엔 keywords 없이 호출 금지 — 생략 시 degraded(품질 낮음) → keywords 추론해 즉시 재호출 필요" 명시.
- `review_regulation` 프롬프트: 1단계에 "keywords는 필수 입력 — 없이 suggest_review_sources 호출 금지", 2단계에 "`keyword_source`가 fallback/client+fallback이거나 note에 `[degraded]` 포함 시, keywords 보강해 재호출한 뒤 그 결과로 검토 진행(degraded candidates만으로 결론 금지)" 추가.

### Tests

- 테스트 **149 → 155**: degraded note 3경로(fallback·early-return·client+fallback)의 `[degraded]` 마커·재호출 지시(`_RECALL_DIRECTIVE`) 포함, **M2 비보류**(degraded여도 candidates 반환) 회귀 가드, 정상 `client` 경로 degraded 미부착, `contract_version` 0.3.0 유지. README 임베드 프롬프트 동기화 가드 통과.

## [0.1.8] - 2026-06-07

`suggest_review_sources` 응답에 **`overflow_candidates`**(cap에 가려진 조문 노출) 추가. `contract_version` 0.2.0 → **0.3.0**(응답 schema additive). 변경은 도구 응답 빌드(요청별 격리)·프롬프트/note 텍스트에 한정 — 부팅·transport·health·캐시 비의존. 목적: 검색·랭킹 알고리즘(v0.1.7)은 그대로 두고, cap(15) 밖으로 밀린 핵심 조문(예: 연구개발비 사용 기준 제74조 "사전 승인 절차")을 호스트가 보고 `get_provision_detail`로 drill-down 하도록 직접 노출(Andy 명시 가치). 설계·"프롬프트 필수 수정" 판정은 `/disc` 3-AI 적대검증 수렴, MCP 응답 한도(25k=token)·응답크기는 라이브 실측으로 확인.

### Added — overflow_candidates 인덱스 (핵심)

- `suggest_review_sources` 응답에 신규 최상위 필드 **`overflow_candidates`**: cap(`_SUGGEST_CANDIDATES_MAX`=15)에 들지 못한 후보를 `{provision_id, label}`로 노출(snippet 없음). `label` 예: "국가연구개발사업 연구개발비 사용 기준 제74조(사전 승인 절차)". cap 선별과 **동일 relevance 기준**(`_relevance_key`) 정렬, `candidates`와 항상 disjoint.
- 신규 필드 **`overflow_truncated`**(bool): cap(`_OVERFLOW_CANDIDATES_MAX`=30) 또는 응답 크기 예산으로 일부 누락 시 `true`. overflow 없으면 `[]`·`false`(두 필드 항상 포함).
- **응답 크기 예산**(`_SUGGEST_RESPONSE_CHAR_BUDGET`=16,000 chars): base 응답(candidates 등) 우선 확정 후 overflow를 잔여 예산 내에서만 추가 — MCP 도구 응답 token hard limit(25,000) 회피용 보수 proxy(서버에 tokenizer 없음, 한국어 char↔token 비율 불확실분 흡수). 라이브 측정: 실제 케이스 전체 응답 15,101 chars(제74조 포함, overflow 30건).
- 신규 헬퍼: `provision_id.unit_label`(JO0074→"제74조", BP0001→"별표 1"), `main._relevance_key`(cap·overflow 공유 정렬키 추출, 동작 보존), `main._overflow_label`, `main._append_overflow_candidates`.

### Changed — 새 필드 활용 안내 동기화 (필수)

- `review_regulation` 프롬프트 2단계: 확인 필드에 `overflow_candidates`·`overflow_truncated` 추가 + truncation 시 overflow_candidates의 provision_id로 직접 `get_provision_detail` 조회하도록 지시(generic — 특정 조문·짝 규칙 아님). 미수정 시 프롬프트-순응 호스트가 새 필드를 우회(search_provision)하여 기능이 inert가 되는 문제 차단(`/disc` 3-AI: 기능적 필수). README 임베드 프롬프트 동기화.
- 서버 truncation `note`·`suggest_review_sources` docstring: overflow_candidates 우선 확인 안내로 갱신(프롬프트와 런타임 지시 일관).

### 검증

- 단위 테스트 138 → **147**(unit_label 2 + overflow shape·정렬·cap·char예산·empty·통합 7). `_relevance_key` 추출은 기존 cap 7테스트가 동작 보존 회귀가드.
- 라이브 종단 검증: 동일 7키워드 케이스에서 contract 0.3.0, overflow 30건·overflow_truncated true, 전체 응답 15,101 chars(≤16k), **제74조(사전 승인 절차) overflow 포함**, candidates와 disjoint 확인.
- **배포 전 라이브 4경로(Claude.ai·ChatGPT·Codex·플러그인) worst-case 스모크가 차단 게이트**: 응답 JSON 무손상·화면 truncation 없음·overflow provision_id로 get_provision_detail 성공 확인 필수(25k=token·Claude.ai 한도 확인불가라 실측으로만 안전 확정).

## [0.1.7] - 2026-06-06

`suggest_review_sources` 검색 랭킹 정상화 + 호스트 키워드 위임 강화. `contract_version`은 **0.2.0 유지** — 응답 필드 추가·삭제·이름변경 없음(`note` 필드 재사용). 변경은 도구 로직(요청별 격리)·프롬프트 텍스트에 한정 — 부팅·transport·health·캐시 비의존. 무게중심을 "fallback 정교화"가 아니라 "호스트가 좋은 키워드를 안정적으로 넘기게 만드는 설계 + 랭킹"으로 이동(설계는 `/disc` 3-AI 적대검증 수렴 + 라이브 재측정으로 효과 확인).

### Changed — 검색 랭킹 (핵심)

- `_select_capped_candidates` 후보 선별 1차 기준을 **제목 매칭 수(title_hits) 우선**으로 변경(정렬키 `(-title_hits, -match_count, rank, provision_id)`). v0.1.6의 match_count-우선은 일반어(정부지원연구개발비/협약/변경)를 우연히 많이 포함한 무관 조문을 정답 위로 올려, 제목이 키워드와 직매칭되는 핵심 조문(시행령 제14조 "협약의 변경"·사용기준 제73조 "사전 승인 대상")을 cap 밖으로 매몰시켰다. title_hits 우선으로 해소.
- v0.1.6의 `_priority`(키워드 배열 앞 index 우선) **제거**: 사용자가 맨 앞에 둔 흔한 키워드를 맞힌 무관 조문이 동률 tie를 싹쓸이(제33조 제재 > 제11조 협약)하던 편향 제거. 동률은 provision_id로 결정(결정성 유지).
- title_hits는 `search_provision`의 토큰 AND/리터럴 의미를 재사용(헬퍼 `_title_token_match`/`_title_hits`). 내부 점수는 후보 응답에 미누설.

### Changed — 호스트 키워드 위임 강화

- `keywords` 입력 description·`review_regulation` 프롬프트 1단계: "사실상 항상 제공" + **질문 원문에 없는 법령 절차어도 추론해 포함**(예: 이관·변경 상황 → 협약변경·사전승인·연구개발과제협약) + 정식 용어 우선 강화. 프롬프트 매칭 설명을 "부분문자열"→"토큰 AND"로 정정(README 임베드 프롬프트 동기화).
- `keyword_source=="fallback"`일 때 응답 `note`에 **품질 저하 경고** 추가(additive — 호스트에 keywords 제공 유도). truncation note와 병기.

### Changed — fallback 안전망(최소)

- 규칙추출 키워드 cap 5 → 10(`_FALLBACK_KEYWORDS_MAX`) + 질문 필러 불용어 확장(참여/중인/올해/구성/싶다 등). 등장순 앞을 점유하던 노이즈를 줄여 핵심어(정출금·연구과업·이관·변경) 추출률 개선. 제목 우선 랭킹이 잔여 노이즈 키워드를 중화하므로 cap 상향이 안전. `_strip_particle`은 불변("기준에→기준에" 등 회귀가드 보존).

### 검증

- 단위 테스트 134 → **138**(title_hits 헬퍼·제목 우선 선별·priority 제거 tie-break·점수 미누설 회귀). 기존 cap 테스트는 title 키 없는 후보에서 title_hits 0 균일 → 비파괴.
- 라이브 재측정(동일 7키워드 client): v0.1.6에서 전부 누락되던 혁신법 제11조·시행령 제14조·사용기준 제73조가 top15 진입, 추가로 제36·62·95·108조(연구개발비 이관 조문)가 부상. 사용기준 제74조(제73조의 절차 조항)는 더 관련 높은 이관 조문에 밀려 1슬롯 차로 미진입 — 제73조 인접 후속조회로 도달 가능, 문서별 phase2 라운드로빈은 v0.1.8 후보.

## [0.1.6] - 2026-06-05

검색 recall·관련도 개선. `contract_version`은 **0.2.0 유지** — 응답 필드 추가·삭제·이름변경 없음. `candidates` 표시 순서(위계순)도 불변이며, 매칭 거동은 결과가 늘어나는 방향(strict superset)이라 클라이언트 호환 깨짐 없음. 변경은 도구 로직(요청별 격리)에 한정 — 부팅·transport·health·캐시 비의존. 참고 자산 `chrisryugj/korean-law-mcp` v4.x(search-normalizer·law-search)의 기법을 본 서버(조문/별표 본문 로컬 검색) 아키텍처에 맞게 적응. 설계는 `/disc`(Claude+Codex+Gemini) 적대적 교차검증으로 수렴.

### Changed — 검색 매칭·관련도 (4 pillar)

- (Pillar C) `search_provision` 매칭을 **토큰 AND**로 확장: query를 공백으로 분해해 2자 이상 모든 토큰이 한 조문/별표의 제목 또는 본문에 있으면 매칭. 단일 토큰 query는 종전 부분문자열 매칭과 동일(동작 불변). 원문이 "협약의 변경/협약을 변경"이라 "협약 변경"이 안 잡히던 띄어쓰기 불일치 해소. snippet anchor는 본문에 존재하는 첫 토큰 기준.
- (Pillar A) `suggest_review_sources` 후보 cap(≤15) **선별 기준을 관련도 우선**으로 변경: 매칭된 distinct 키워드 수가 많은 후보가 위계·조문번호만 앞선 총칙 조문에 밀려 cap 밖으로 탈락하던 문제 해소. 관련도 동률이면 종전 (중요 키워드, 위계, provision_id) tie-break. 표시 순서·`recommended_review_order`는 위계순 유지(검토는 상위법부터).
- (Pillar B) **R&D 도메인 동의어 1-hop 확장**: 현장용어·법령별 표기차(정출금↔정부지원연구개발비↔출연금↔정부출연금, 협약변경↔협약 변경 등)를 `suggest_review_sources` 내부에서만 변형으로 확장해 union 검색. `matched_keywords`는 origin 키워드만 기록(관련도 부풀림 방지), 동일 term 1회만 호출(memoize), 총 검색 term ≤16 cap. `search_provision` 직접 호출에는 미적용.
- (Pillar D) fallback 키워드 추출 보수적 개선: 속격 조사 "의" strip 추가(len-guard로 "정의"·"협의" 등 짧은 명사 보존), 노이즈 불용어(일부/다른/해당/여부/위해/통해) 추가. `keywords` 입력 description을 토큰 AND·정식 용어 우선·동의어 자동확장 안내로 갱신.

### Fixed — 배포 전 적대 검증(/goal-disc-out 2라운드)에서 발견한 recall 회귀

- (S1) `search_provision`의 토큰 분해를 **의미 토큰(2자 이상) 2개 이상일 때만 토큰 AND**, 그 외에는 리터럴 query로 검색하도록 수정. 기존 `[t for t in query.split() if len(t)>=2] or [query]`는 "별표 1"(단어+한 자리 숫자)에서 "1"이 탈락해 "별표" 1토큰으로 과확장 → 59건 superset이 `_RESULTS_MAX`(30) truncation에 걸려 **리터럴 "별표 1" 18건 중 12건(실제 별표 1 포함) 유실**되던 회귀. 수정 후 "별표 1"은 리터럴 매칭(v0.1.5 동작)으로 복귀하고 "협약 변경"(의미토큰 2개)은 토큰 AND 유지.

### 검증

- 단위 테스트 120 → **134** (Pillar별 회귀·false-positive + S1 "별표 1" 리터럴·다중토큰 AND 보존). `_select_capped_candidates` 기존 4 테스트는 관련도 동률 조건에서 종전 동작과 동일하게 유지.
- 로컬 서버 부팅 스모크(도구 등록·`--http` 기동) 배포 전 수행.
- **알려진 한계(v0.2 과제)**: fallback `_strip_particle`이 속격 "의"를 strip하면서 "사전심의→사전심"처럼 명사 일부 "의"인 복합어를 prefix로 자름(recall은 prefix로 보존, fallback 전용). 2자 "X의" 예외목록 방식은 "규정의/개발의/조문의" 같은 핵심 속격을 오보존해 net-negative라 미채택 — 형태소 분석이 필요해 v0.2로 이월.

## [0.1.5] - 2026-06-04

`suggest_review_sources` 도구의 입력·출력 개선. `contract_version` 0.1.0 → **0.2.0** (minor bump — 응답 additive 필드 추가 + `candidates` 거동 변경. 0.x 대역이라 minor도 breaking 허용. `docs/api_contract.md` §5.1·5.2·6 참조).

### Added — 검색 키워드 위임 (A축)

- `suggest_review_sources`에 선택적 `keywords: list[str] | None` 입력 추가. 호스트 LLM이 question에서 직접 추출한 검색어 배열을 우선 사용하고, 생략·무효 시 서버 규칙 추출(`_extract_keywords`)로 fallback. 정규화: 문자열만·공백 제외 2자 이상·순서 보존 dedupe·최대 10개.
- 클라이언트 키워드가 0건 + 오류 없음이면 규칙 추출로 보강(`client+fallback`) — recall 저하 방지. 클라이언트 검색에 오류가 있으면 보강 생략(원인 은폐 방지).
- 응답 additive 필드 `keyword_source`(`client`|`fallback`|`client+fallback`). `extracted_keywords`는 실제 검색에 사용된 키워드 반환.
- `review_regulation` 프롬프트·README: 1단계에서 검색 키워드 배열을 작성해 `keywords`로 전달하도록 안내.

### Changed — 응답 크기 상한 (B축)

- `suggest_review_sources` 반환 `candidates`를 위계·중요도 상위 최대 **15건**으로 cap. 매칭 문서 수가 15 이하면 각 문서 최소 1건 보장, 초과 시 위계 상위 문서 우선(탈락 문서는 `recommended_review_order`로 안내). 반환 후보 `snippet`은 ≤300자로 단축. MCP 단일 응답 토큰 한도(25,000) 회피.
- 응답 additive 필드 `returned`·`truncated`·`note`. `total`·`recommended_review_order`는 cap 이전 전체(suggest 내부 후보 풀) 기준 — truncation 복구 경로.
- 프롬프트·README 2단계: `truncated`가 true이면 `recommended_review_order`·`search_provision`으로 누락 후보를 보완하도록 안내.

### Fixed

- `_shorten_snippet`에 None·빈 값 가드 추가(잠복 TypeError 방어).
- `docs/api_contract.md` §5.2 문구 정정: 완결성 범위를 suggest 내부 후보 풀 기준으로 한정(개별 `search_provision`은 `_RESULTS_MAX`로 별도 제한), 토큰 경고 임계 문구 완화.
- 회귀 테스트 보강(경계·rank 동률 결정성·snippet 방어·client+fallback→cap 결합 등). 전체 120 passed.

## [0.1.4] - 2026-05-31

### Fixed — 현행 시행일 정합성 (안정적 일련번호 행정규칙 개정 감지)

표시되는 시행일자가 옛 manifest 값에 박제되어, 본문은 현행을 가져오면서도 사용자에게 "오래된 문서를 참조 중"으로 보이던 결함 수정. `contract_version` 0.1.0 유지 (기존 응답 필드 제거·이름 변경 없음 — `effective_date` 등 additive 필드만 추가하고 값 출처·표시 조건 보정. 하위 호환).

- 표시 `effective_date`를 LIVE resolve 값 우선으로 변경 (`get_provision_detail`, `search_provision` 결과). resolve 실패 시에만 manifest 값 폴백.
- 개정 감지 신호를 `doc_id 변경` 외에 `LIVE 시행일 ≠ manifest 시행일`로 확장. law.go.kr 행정규칙은 개정돼도 일련번호가 유지되는 경우가 있어 기존 `doc_id` 비교만으로는 개정을 놓침 (연구개발비 사용 기준 사례). LIVE 값이 비어있으면 개정 판단 보류 (오탐 방지).
- `search_provision` 각 결과에 `effective_date` 상시 첨부 (additive). `revision_notice`는 개정 감지 시에만.
- `rule_sets.yaml` `rnd_funding_standard` 시행일자 `2024-06-13` → `2026-05-06` 데이터 수정 (LIVE 검증, 일련번호 2100000278740 불변). 전수 감사 결과 stale 항목은 이 1건뿐.

### Changed — review_regulation 프롬프트 강화

프롬프트 텍스트만 수정 (도구 로직·`contract_version` 0.1.0 불변). PyPI·플러그인이 NAS보다 뒤처져 있던 프롬프트를 본 release로 동기화.

- 검토 절차 6번을 "조문 요건 해석 + 사실관계 1:1 대조(충족/불충족/사실부족/규정미확인/MCP범위밖) + 상위 규정 우선"으로 강화. 출력에 "6. 쟁점·결손 분석" 도입, 근거 조항 "적용" 줄에 판단단위·충족 여부 구체화.
- `suggest_review_sources` 호출 안내의 따옴표 충돌 정리: `situation`에 큰따옴표 포함 시 `question="..."` 중첩으로 안내가 모호해지던 것을 지시문 형태로 변경.

### Security — 키/OC 누설 회귀가드 보강 (테스트 전용)

- per-user OC key(HTTP `?oc=` contextvar 경로) 누설 부재를 `health`·`get_provision_detail`·`suggest_review_sources` 응답에 대해 회귀테스트로 고정.
- `_request_with_retry` 로그에 키 값·앞자리·`OC=` 미포함(type 이름만 로깅) 회귀테스트 추가.

### Removed — 미사용 코드 제거

- `live_api.py`의 미사용 `ProvisionRef` dataclass·`ERROR_INVALID_PROVISION_ID` 상수 제거 (동작·contract 불변; `invalid_provision_id` 오류코드는 그대로 유지).

### Docs

- README 동기화: 지원 규정 헤더 `v0.1.3` → `v0.1.4`, `rnd_funding_standard` 시행일 `2024-06-13` → `2026-05-06`, 테스트 수 `86` → `95`.

### Tests
- 10개 신규 테스트 추가 (86 → 96개): 시행일 정합성 4건(helper 4분기 lock·안정적 일련번호 개정 감지 2건·manifest 데이터 lock) + 보안 회귀가드 4건(per-user OC ×3·로그 누설) + 프롬프트 따옴표 회귀 1건 + README↔프롬프트 동기화 가드 1건.

## [0.1.3] - 2026-05-28

### Added — 국토교통 R&D family 4건 manifest 추가 (additive only)

기존 13개 rule set은 그대로 유지하고, 국토교통 R&D 분야 특화 규정 4건을 추가하여 17개로 확장. `contract_version` 0.1.0 유지, 응답 schema·기존 검색 결과 불변.

- `sector_kt_act` — 국토교통과학기술 육성법 (법률, MST 268733, 2026-02-01 시행, 조문 19)
- `sector_kt_decree` — 동 시행령 (대통령령, MST 264735, 2024-08-07 시행, 조문 13)
- `sector_kt_rule` — 동 시행규칙 (국토교통부령, MST 203848, 2018-06-08 시행, 조문 7)
- `kt_rnd_operations` — 국토교통부소관 연구개발사업 운영규정 (admrul ID 2100000235502, 2024-01-22 시행, 조문 44 + 별표 5)

### Tests
- 2개 신규 테스트 추가 (84 → 86개): sector family entries 존재 검증·hierarchy_rank 정렬 검증
- `test_list_rule_sets_returns_live_api_items`: total 13 → 17 갱신

[0.1.4]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.4
[0.1.3]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.3

## [0.1.2] - 2026-05-27

### Changed — HTTP 모드 + review prompt 개선

- `search_provision` 13개 rule set 상세조회를 `asyncio.gather`로 병렬 실행 (순차 → 병렬)
- `search_provision` 결과 수 제한 (`_RESULTS_MAX = 30`, `returned`/`truncated` 필드 추가)
- `health` 도구가 per-user OC key (contextvar) 설정 여부도 반영
- `review_regulation` prompt 전면 개선:
  - `search_provision` 추가 검색 단계 도입
  - 참조 조항 추적·법적 판단 기준(재량/의무·상위법 우선) 명시
  - 출력 형식 7섹션 구조화 + 표현 판단 태그
  - MCP 적용 범위·미커버 영역 명시 + verbatim 인용 보호

### Added

- Claude Code 플러그인 마켓플레이스 지원 (`.claude-plugin/plugin.json`, `marketplace.json`)
  - `uvx` 기반 실행으로 사전 `pip install` 불필요
  - 설치: `/plugin marketplace add smilemin07/korean-rnd-regs-mcp`

### Tests
- 3개 신규 테스트 추가 (81 → 84개): truncation 동작, response shape 보강

[0.1.2]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.2

## [0.1.1] - 2026-05-25

### Fixed — search-first 패턴 (규정 개정 자동 반영)

- 규정 개정 시 최신 버전을 자동으로 조회하는 search-first 패턴 추가 (`resolve_latest_doc_id`)
  - 도구 호출 시 manifest의 규정명으로 검색 API를 먼저 호출하여 최신 문서 ID 확인
  - 개정이 감지되면 최신 ID로 상세 조회 + 응답에 `revision_notice` 필드 포함
  - 검색 실패 시 manifest ID로 fallback (기존 동작 유지)
  - 24시간 캐시로 반복 호출 시 추가 API 비용 없음, 실패는 5분 캐시로 빠르게 복구
- `get_provision_detail`: resolved doc_id로 provision_id가 전달될 때 manifest lookup fallback 추가
- title matching에 Unicode 중간점 정규화 추가 (`ㆍ` U+318D → `·` U+00B7)
- `suggest_review_sources`: search-first로 doc_id가 변경되어도 정상 동작하도록 `rule_set_id` 기반 lookup으로 변경

### Tests
- 14개 신규 테스트 추가 (67 → 81개): resolve 동작·fallback·캐시·중간점·최신 날짜 선택·보안 회귀

[0.1.1]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.1

## [0.1.0] - 2026-05-24

### Added — 첫 publish

#### MCP Tools (5종)
- `health` — 서비스 상태·API 키 설정 여부 확인
- `list_rule_sets` — 등록된 규정 목록 조회
- `search_provision` — 조문·별표 본문 키워드 검색 → snippet + provision_id list
- `get_provision_detail` — provision_id로 단일 조문/별표 본문 verbatim 조회
- `suggest_review_sources` — 자연어 질문 → 키워드 추출 → 검토 후보 + 추천 순서

#### MCP Prompts (1종 — v0.2 plan 1·3 보강을 v0.1.0에 미리 포함)
- `review_regulation` — 다층적 규정 검토 워크플로 자동 적용. Claude Desktop의 prompts 메뉴에서 선택 시, 본 server의 13개 규정을 위계 순서로 cross-reference하여 근거 조항 verbatim 인용과 함께 답변. 본 프로젝트 저자의 표준 규정 검토 워크플로 패턴(Tier 1 → Tier 2 → Supplementary, provision_id verbatim 인용)을 본 server 도구 호출 형태로 자동화 — 외부 사용자도 별도 skill 설치 없이 표준 워크플로 기반의 1차 검토 가능. 단, 매뉴얼·부처별 운영규정·관리지침은 본 server 미커버 (별도 자료 확인 필요)

#### Manifest (13개 rule set — 4개 MVP + 9개 v0.2 보강을 v0.1.0에 미리 포함)

Tier 1 — 핵심 법률·시행령·시행규칙 (혁신법 family):
- `innovation_act` — 국가연구개발혁신법 (법률, MST 260807, 2025-02-28 시행)
- `innovation_decree` — 동 시행령 (대통령령, MST 285767, 2026-05-06 시행)
- `innovation_rule` — 동 시행규칙 (과기정통부령, MST 285043, 2026-03-25 시행)

Tier 2 — 핵심 행정규칙 (핵심 행정규칙):
- `rnd_funding_standard` — 국가연구개발사업 연구개발비 사용 기준 (admrul ID 2100000278740, 2024-06-13)
- `simultaneous_research_limit` — 국가연구개발사업 동시수행 연구개발과제 수 제한 기준 (2100000196149, 2021-01-01)
- `facility_equipment_standard` — 국가연구개발 시설·장비의 관리 등에 관한 표준지침 (2100000278230, 2026-04-23)
- `research_note_guideline` — 국가연구개발사업 연구노트 지침 (2100000207982, 2022-01-01)

Supplementary — 신고·포상금·부패행위·청탁금지·공익신고자보호 cross-reference:
- `anti_corruption_act` / `anti_corruption_decree` — 부패방지 및 국민권익위원회의 설치와 운영에 관한 법률 (+ 시행령) (MST 268657 / 283781)
- `improper_solicitation_act` / `improper_solicitation_decree` — 부정청탁 및 금품등 수수의 금지에 관한 법률 (청탁금지법/김영란법) (+ 시행령) (MST 268655 / 281817)
- `public_interest_whistleblower_act` / `public_interest_whistleblower_decree` — 공익신고자 보호법 (+ 시행령) (MST 268861 / 264451)

#### Infrastructure
- live_api 트랙: 국가법령정보 OpenAPI(lawSearch.do, lawService.do) 기반 검색·상세조회
- provision_id 포맷 `{doc_type}:{doc_id}[:{unit_id}]` — JO(조문) / BP(별표) prefix 지원
- API contract v0.1.0 ([docs/api_contract.md](docs/api_contract.md))
- LawApiClient + TTLCache (24h success, 5min failure)
- Pydantic RuleSet schema (14 fields, extra="forbid")
- FastMCP 3.3 stdio mode + prompts 지원
- 행정규칙 schema 2종 모두 지원: 표준 `<조문단위>` 구조 + 평면 `<조문내용>` (root 직속) fallback (LIVE 검증: 동시수행 과제 수 제한·연구노트 지침 등)

#### LLM 환각 방어 (additive metadata)
- `get_provision_detail` 응답에 `content_format: "plain_text_verbatim"` marker
- `format_instructions` field (LLM 표시 정책 명시)
- `article_structure` (machine-readable nested hierarchy: title / paragraphs[].number / text / source_text / subparagraphs)

### Security
- LAW_API_KEY 누설 차단 다중 layer:
  - `_request_with_retry`: `requests.exceptions.RequestException` 포괄 catch + type 이름만 사용 (URL/key 미노출)
  - `_sanitize_error_message`: 도구 응답 직전 second-layer redact
  - 응답·로그·error message 어느 곳에도 키 원문·앞자리·hash 미포함
- 회귀 테스트 다수 포함 (test_*_no_key_leak, test_live_api_handles_sslerror_without_url_leak)

### Tests
- 67 unit tests (mock 기반, 네트워크 미사용) — manifest 13건 검증, prompt template substitution, schema B fallback 등 포함
- LIVE API 통합 테스트는 v0.2에서 @pytest.mark.network 마커로 분리 예정

### Known Limitations (현재 미지원)
- 가지조문(예: 제15조의2): 현재 provision_id 포맷이 `JO` + 숫자만 지원 — 검색·상세조회에서 누락
- 법령 시행령 별표(혁신법 시행령 별표 1~7 등): 현재 `unit_types: article`로 설정되어 별표 미검색
- PDF 색인·OCR·SQLite FTS5 (기관별 운영규정·매뉴얼): 향후 확장 예정

[0.1.0]: https://github.com/smilemin07/korean-rnd-regs-mcp/releases/tag/v0.1.0
