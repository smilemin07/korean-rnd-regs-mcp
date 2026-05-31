# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 형식을 따릅니다.
버전 번호는 [Semantic Versioning](https://semver.org/lang/ko/) 2.0.0을 따르되, 0.x.x 대역은 unstable signal이며 minor bump도 breaking change 허용입니다.

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
