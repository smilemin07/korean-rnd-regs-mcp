# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 형식을 따릅니다.
버전 번호는 [Semantic Versioning](https://semver.org/lang/ko/) 2.0.0을 따르되, 0.x.x 대역은 unstable signal이며 minor bump도 breaking change 허용입니다.

## [0.2.4] - 2026-06-12

**검증 후속 보정 — 혁신법 현행 시행일 정합 + 토큰별 매칭 행 보장** — v0.2.3 배포 직후 수행한 전수 감사(/regs-audit)와 라이브 eval에서 실증된 정합 결함 2건을 마감. `contract_version` **0.5.0 유지**(응답 schema·필드 무변, `_SNIPPET_MAX` 2000 불변). 변경은 manifest 데이터·순수 함수(`_annex_snippet` 수집부)·테스트에 한정 — 부팅·HTTP transport 비의존(outage 무위험).

### Fixed

- **혁신법 family manifest 현행화**(2026-06-11 시행 개정 발효분, LIVE 감사 + 적대 교차검증 confirmed): 국가연구개발혁신법 api_doc_id 260807→**283849**·시행일 2026-06-11 / 시행규칙 285043→**286879**·시행일 2026-06-11 / 시행령 시행일만 2026-05-06→**2026-06-11**(MST 불변). search-first 자동 resolve라 런타임 정확성은 종전에도 정상 — fallback 값·표시 시행일 정합 회복. 주의: 합본 MST의 상세응답 시행일자는 미래 분리시행분(283849→2026-09-11)이라 검색 행 기준으로 채택.
- **별표 스니펫 토큰별 매칭 행 quota**: 매칭 줄 수집을 "문서 순서 합집합 cap 6"에서 "토큰별 ceil(cap/토큰수)개 선확보 + 잔여 cap 문서 순서 충원"으로 보정 — 빈출 토큰(반복 표 머리글 등)이 cap을 선점해 희소 토큰의 매칭 행이 침묵 탈락하던 기아 해소(라이브 실증: "간접비 서울대학교" 질의에서 간접비 머리글 5줄이 cap 소진 → 본교 행 27.01 탈락·재검색 1회 유발). 단일 토큰 질의 동작 불변.

### Tests

- 토큰별 quota 기아 회귀 1건 추가 + mock 혁신법 doc_id 리터럴 신 MST(283849) 정렬. 전체 195 → **196**.

## [0.2.3] - 2026-06-12

**대용량 별표 핀포인트 도달성 복구** — oversized 대용량 별표(예: 연구개발비 사용 기준 별표 6 간접비고시비율, 21,341자·633줄)에서 질의 토큰의 매칭 행이 여러 곳일 때 `search_provision` 스니펫이 첫 매칭 줄 1곳만 발췌해 핵심 행에 도구만으로 도달 불가하던 결함을 해소(예: "서울대학교" 질의 시 앞쪽 "남서울대학교" 행에 발췌가 선점돼 본교 행 27.01 미포함 — 라이브 실사용 실측). `contract_version` **0.5.0 유지**(응답 schema·필드 무변 — 신규 필드 없음, `_SNIPPET_MAX` 2000자 불변, 검색·랭킹·fallback 알고리즘 불변). 변경은 순수 함수(`_annex_snippet`)·호출부 1곳·응답 안내 텍스트·테스트에 한정 — 부팅·HTTP transport·캐시·OC 미들웨어 비의존(outage 무위험).

### Added

- **별표 스니펫 마커 2형 분기**: 별표 본문 전체가 스니펫에 수록되면 "발췌" 대신 전체 수록임을 표기, 일부만 수록되면 "매칭 행 중심 발췌 — 발췌 행 자체는 원문 그대로, 표 제목·인접 행 누락 가능, 전문은 get_provision_detail 또는 공식 원문 확인" 취지의 마커 부착(별표 전체 인용 금지 신호와 의미 구분). 종전에는 전체 수록 시에도 "발췌"로 오표기. `suggest_review_sources` 후보 snippet(300자 절단)에서는 별표 마커를 제거 — 절단본에 "전체 수록" 주장이 잔존하는 오신호 방지.

### Fixed

- **대용량 별표 멀티 매칭 행 발췌**(`_annex_snippet` 멀티윈도우 개편): 질의 전 토큰의 매칭 줄 합집합(중복 제거·문서 순서 유지·cap 6) + 각 매칭 줄 ±1줄 맥락 윈도우 + 중첩 윈도우 병합 + 예산(`_SNIPPET_MAX` 2000 − 마커) 내 앞 윈도우 우선 배치 + 잔여 예산 라운드로빈 줄 확장(단일 매칭 시 종전과 동등한 풍부함) + 비연속 윈도우 사이 "…" 구분 줄. 개행 없는 장문 char 절단 폴백 유지. 호출부도 본문 존재 전 토큰 전달로 일반화(종전: 첫 토큰 1개). 종전 anchor 첫 매칭 줄 1곳 발췌가 후순위 매칭 행을 침묵 누락하던 결함 수정.

### Changed

- **oversized_pointer 안내 문구**: `content` 포인터·`required_action`에 ① `document_source_url`(법제처 공식 원문)을 1순위로 명시 ② `attached_file_url` 첨부는 HWP·HWPX 등 기계 열람이 불가할 수 있는 형식이라는 보수 문구 추가(라이브 실측: 별표 6 첨부 = .hwpx — 호스트 기계 열람 불가가 웹 방랑을 촉발). 기존 "이 안내 텍스트를 규정 원문으로 인용하지 마십시오" 신호 보존. 필드 구성 무변.

### Tests

- `_annex_snippet` 멀티윈도우(사례0 폐쇄 회귀·"…" 구분/예산/줄경계·마커 2형·인접 매칭 병합·다중 토큰 합집합) + search_provision 호출부 통합 가드(전 토큰 전달) + suggest 후보 마커 제거 + oversized_pointer 신규 문구 회귀 — 신규 9건. 기존 2건은 호출 인자만 list로 갱신(단언 무수정). 전체 186 → **195**.

## [0.2.2] - 2026-06-11

**별표 발견성 마감 — 호스트 오도·막다른 길 신호 제거** — v0.2.1이 데이터(doc-level 별표 목록·가지별표 BP)로 연 별표 발견 경로의 잔여 마찰을 기존 텍스트 채널(`warnings`·오류 `message`·프롬프트)만으로 마감. 별지·서식 BP 미노출을 모르는 호스트의 막다른 길, BP `not_found` 후 복구 경로 부재, v0.2.0~0.2.1 별표 지원을 "미지원"으로 덮던 stale 안내 문구를 제거. `contract_version` **0.5.0 유지**(응답 schema·필드 무변 — 신규 필드 없음, 검색·랭킹·fallback 알고리즘 불변). 변경은 응답 텍스트·프롬프트·테스트·Docker 빌드 핀에 한정 — 부팅·HTTP transport·캐시·OC 미들웨어 비의존(outage 저위험).

### Added

- **별지·서식 막다른 길 신호**: 별지·서식 보유 문서의 document-level 응답 `warnings`에 "별지·서식 N건은 본 도구로 본문 조회 불가 — document_source_url의 공식 원문에서 확인" 1줄 — 호스트가 존재하지 않는 별지 BP를 헛검색하는 경로 차단. document-level `annexes`에 `dependent_article_hints`가 있으면 미검증 단서 경고 1줄도 동봉(별표 상세의 기존 note와 정합).
- **오류 복구 안내 텍스트**: ① BP `not_found` 메시지에 "별표 번호를 추측해 재시도하지 말 것 — unit_id 없이 문서를 조회해 annexes 목록에서 선택" 복구 경로 안내 ② `auth_failed` 메시지에 원격(HTTP) 모드의 `?oc=` URL 파라미터 확인 안내 병기(키 값 미포함) ③ `review_regulation` 프롬프트에 degraded 재호출 종료조건 1줄(최대 1회 — README 임베드 동기화) — 모두 기존 필드의 텍스트만, 신규 필드 없음.

### Fixed

- **stale 안내 문구 정정**: manifest `known_limitations`의 "별표·서식 검색은 v0.2 deferred" 등 v0.2.0~0.2.1 별표 지원을 부정하던 문구 4건을 현행 거동(document-level 목록·BP 상세 접근 가능)으로 갱신 — 공익신고자 보호법 시행령 별표 1의2 등 v0.2.1 수혜 경로를 경고문이 가리던 active-harm 해소. "별표 30개 모두 검색"(실제: 별표 8 + 별지 22) 등 과대 기술 2건과 가지조문 "v0.2 예정" 시점 표기, `search_provision` docstring의 law 별표 검색 미반영도 함께 정정.
- `docs/api_contract.md` 헤더 개정일에 0.5.0(2026-06-10) 누락 보충.

### Changed

- **Dockerfile fastmcp 핀**: `pip install`에 `fastmcp==3.4.2`(NAS 라이브 v0.2.1 이미지 실측 버전) 추가 — uvicorn==0.48.0·python-multipart==0.0.30과 동일한 "라이브 검증 버전 핀" 정책으로 재빌드 시 서버 프레임워크 자동 업데이트로 인한 --http 거동 변화 차단. 런타임 코드 무변(pyproject 범위 `fastmcp>=3.3,<4` 불변 — stdio/pip 설치 사용자 영향 없음).

### Tests

- admrul 별표 파서의 v0.2.1 신규 필드(`별표구분`·`별표가지번호`·제목 unescape) 캡처 회귀 + admrul document-level `annexes` 목록 경로 + `suggest_review_sources` fallback+truncated 결합 note 전용 테스트. 전체 183 → **186**.

### Repo

- **pytest CI 신설**: `.github/workflows/tests.yml` — push/PR 시 단위 테스트 자동 실행(mock 기반·네트워크/secrets 불요).
- **Fly.dev 자동 배포 제거**: `.github/workflows/fly-deploy.yml` 삭제 — Fly.dev는 NAS 배포 전환 후 미사용이며, main push마다 통제 밖 섀도 배포가 발생하던 경로 차단(GitHub 워크플로 비활성 처리 병행).
- `.gitignore`에 `uv.lock` 추가(본 프로젝트는 uv 미사용).

## [0.2.1] - 2026-06-10

**별표 발견성·정확 선택 강화** — v0.2.0 첫 실사용에서 호스트 AI가 라벨 없는 `annexes_count` 정수만 보고 별표를 추측 선택(운으로 적중)한 갭을 데이터(제목 목록·의존조문 단서)와 프롬프트(동반조회)로 폐쇄. 동시에 LIVE 실측으로 발견한 **가지별표 미인식·별지/서식 BP 충돌(오도달)** 현존 결함을 수정. `contract_version` **0.5.0**(0.4.0 → minor bump). 설계는 17-에이전트 후보 분석 + `/disc` R1 + 6-에이전트 구현 실측 + `/goal-disc-out` R2 적대 재검증(blocking 0 수렴)으로 확정. 변경은 파서·응답 조립·프롬프트·동의어 사전에 한정 — 부팅·HTTP transport·캐시·OC 미들웨어 비의존(outage 저위험).

### Added

- **document-level 별표 목록**: `get_provision_detail`(unit_id 생략) 응답에 `annexes: [{provision_id, label, title, dependent_article_hints?, deleted?}]` — 호스트가 추측 대신 제목을 보고 BP를 선택. 본문 미포함(최악 문서 실측 +3.0k chars, 16k 예산 내). `annexes_count`는 종전 의미(전건 집계) 유지, 구성은 신규 `annexes_count_by_kind`(예: 별표 8·별지 22)로 표시.
- **가지별표 인식**: OpenAPI `별표단위`의 `별표가지번호`·`별표구분` 파싱 추가. 가지별표는 6자리 BP id(`BP{번호4}{가지2}`, 예: `BP000102`=별표 1의2)로 검색·상세·목록에서 도달 가능(이전: 주소 자체가 없어 도달 불가 — 공익신고자 보호법 시행령 별표 1의2 등). 본별표의 기존 4자리 id는 불변(하위호환). `unit_label` 가지-aware("별표 1의2").
- **별표 의존조문 단서**: 별표 제목의 조문 참조("(제19조제3항 관련)")를 전건 추출한 `dependent_article_hints`(복수 list, 미검증 단서 명시 note 동봉) — 별표 상세 + document-level 목록 항목. `review_regulation` 프롬프트 5단계에 동반조회(1-hop 한정·힌트 자체 인용 금지)·문서레벨 목록 선택(추측 BP 조회 금지) 지시 2건 추가(README 임베드 동기화).
- **별표 파싱 실패 정직성**(law 한정): document-level에 `annexes_unavailable`·`annex_parse_error` 표면화 — `annexes_count=0`이 "별표 없음"으로 오인되는 거짓 신호 차단.
- **현장어 동의어(단방향 alias)**: "정부출연연구비"·"정출연연구비"·"출연연구비" → 정식어(정부지원연구개발비 등) 확장. corpus-dead(LIVE 0건) 현장어라 역방향 미확장으로 16-term cap 보호(suggest 경로 전용, 응답 schema 무관).

### Fixed

- **별지·서식 BP 충돌(오도달) 버그**: `별표구분`이 '별지'·'서식'인 항목은 별표와 번호가 독립 채번이라 같은 BP id로 충돌(별표1·별지1 모두 BP0001) — 별지 검색 결과를 조회하면 동번호 별표가 반환되던 결함. 별지·서식을 검색·상세 매칭·목록에서 제외(별지만 매칭되던 질의는 결과 감소 가능 — 공식 원문은 `document_source_url`).
- **BP 우연 첫-일치 제거**: `get_provision_detail`(BP)을 (번호, 가지) 엄격 매칭으로 — 없는 별표는 `not_found`(엉뚱한 별표 반환 차단).
- **별표 제목 이중 이스케이프**: 소스가 CDATA 안에 사전 이스케이프 텍스트를 송신하는 경우(삭제 별표 제목 "삭제 &amp;lt;날짜&amp;gt;")를 live_api 파서 단일 관문에서 `html.unescape`. 삭제 별표 판정을 제목 기반("삭제" 정확 일치·"삭제 <" 시작)으로 보강 — admrul 삭제 별표("<삭 제>" 공백형)도 `deleted_stub`로 정합 분류.

### Changed

- `provision_id`: `_UNIT_PATTERN`을 BP 4자리(본별표)/6자리(가지별표) 한정으로 협소화 — 5자리 등 디코드 의미 미정의 입력은 `invalid_provision_id`(종전 "4자리 이상" 대비 형식적 변경, 서버 발급 이력은 4자리뿐이라 실영향 0). `docs/api_contract.md` §5.6 신설, `contract_version` 0.4.0 → **0.5.0**. 테스트 168 → **183**.

## [0.2.0] - 2026-06-09

**법령(시행령) 별표 추출 지원** — 그동안 행정규칙 별표만 가능하고 법령 별표는 미지원이던 한계를 해소. 국가연구개발혁신법 시행령 별표 1~7(정부지원 지원기준·연구개발비 사용용도·등록범위·참여제한·제재부가금 등 — 실제 답이 되는 수치가 담긴 부분)을 `search_provision`·`get_provision_detail`로 조회 가능. OpenAPI에 inline 텍스트로 존재함을 LIVE 확인했고, `get_law_detail`이 `<별표단위>`를 파싱하도록 확장(PDF/OCR 불필요). `contract_version` **0.4.0**(0.3.0 → minor bump — 응답 schema additive 필드 추가). 설계·구현은 `/goal-disc-out` 2라운드 3-AI 적대검증으로 수렴(blocking 3건 사전 차단). 변경은 도구 fetch·검색·상세 로직(요청별 격리)에 한정 — 부팅·HTTP transport·캐시·OC 미들웨어 비의존(outage 저위험).

### Added

- **법령 별표 파싱** (`live_api.get_law_detail`): `<별표단위>` → `별표번호/별표제목/별표내용/별표서식파일링크`. **fault-isolation** — 별표 파싱 실패가 기존 조문(articles) 반환 경로를 깨지 않도록 독립 try/except로 격리하고 실패를 `annex_parse_error`로 표면화.
- **size-tiered `get_provision_detail`(별표)**: 직렬화 응답이 보수 예산(`_ANNEX_DETAIL_CHAR_BUDGET`=16,000 chars) 이내면 본문 전문(`content_format=plain_text_verbatim`); 초과(별표2 17,480자·별표7 17,949자)하면 본문 미수록 + 신규 필드 `content_available`·`content_format=oversized_pointer`·`is_complete`·`omitted_reason`·`omitted_char_count`·`required_action`·`verbatim_quote_allowed`. 본문 없는 서식파일 별표 → `external_file_only`. 삭제 별표 → `annex_status=deleted_stub`.
- **별표 전용 줄단위 스니펫**(`_annex_snippet`): 공백 정렬 표의 행 중간 절단을 막기 위해 개행 경계로 자르고 "발췌·표 원문 확인" 마커 부착. 별표 파싱 실패는 `search_provision` errors에 `annex_parse_failed`로 노출.

### Changed

- `rule_sets.yaml` `innovation_decree.unit_types`: `article` → **`both`**(별표 검색·상세 활성화). known_limitations의 "별표 검색 v0.3 이후 가능" 문구를 v0.2 지원·size-tiered 안내로 정정.
- `review_regulation` 프롬프트: "시행령 별표 미커버/fetch 불가" 문구 정정 + **`content_format`이 `plain_text_verbatim`이 아니면 그 content를 규정 원문으로 인용 금지·공식 원문 확인** 규칙 명문화. README 임베드 사본 동기화.
- `docs/api_contract.md`: §5.5 신설 + "`get_provision_detail` 본문 길이 제한 없음" 문구 정정 + 0.4.0 이력. `contract_version` 0.3.0 → **0.4.0**.

### Notes

- 대용량 별표(별표2·7) 전문 제공은 **보수적으로 보류**(ChatGPT MCP 응답 한도 확인 불가 + 한국어 char↔token 비율 불확실) — LIVE 4경로 실측 통과 후 별도 최적화로 상향 검토.

### Tests

- 별표 신규 12건(`_build_annex_detail` 전문/포인터/외부파일/삭제stub·예산 준수, `_annex_snippet` 마커·줄경계·개행없는 장문 안전절단, 법령 별표 BP 조회, 파서 실패 표면화, both-empty external_file_only, 삭제 동사 오탐 방지). contract_version 핀 0.4.0 갱신. 전체 **168**.

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
