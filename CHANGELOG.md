# Changelog

본 파일은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 1.1.0 형식을 따릅니다.
버전 번호는 [Semantic Versioning](https://semver.org/lang/ko/) 2.0.0을 따르되, 0.x.x 대역은 unstable signal이며 minor bump도 breaking change 허용입니다.

## [0.21.1] - 2026-07-22

**근거 법률 인용 원문 단위 보존 — 개정문 인용 시 조문번호 탈락 방지 프롬프트 정밀화** — v0.21.0 배포 후 브라우저 라이브 eval(2026-07-21·PASS_WITH_MINOR·날조 0·서버 결함 0)의 유일 minor: 호스트가 개정문(amendment_text)의 제10조 개정후 대체문을 인용하며 "「중소기업진흥에 관한 법률」 제68조에 따른 중소벤처기업진흥공단"에서 조문번호("제68조에 따른")만 탈락(법명·기관명은 보존·같은 답변 다른 항목에선 보존=다중 항목 나열 시 표본 이탈·v0.17.0 minor③[기관명-만 축약]의 재발 계열). 근본원인 = 기존 지시가 "기관명만으로 축약하지 말고"에 초점이라(v0.17.1 도입 당시 사건 대응형) 조문번호-만 탈락 케이스를 못 겨냥 + LLM의 가독성 요약 성향이 다중 항목에서 보존 지시를 표본적으로 압도. 해당 지시 1문장을 in-place 강화하는 **프롬프트 문자열-only patch**(v0.17.1·v0.19.1·v0.20.1과 동형): 근거 법률 인용구는 법명·조문번호·'에 따른' 연결어를 포함한 **원문 단위 그대로 보존**('「법명」 제N조에 따른 기관' 패턴 등에서 '제N조에 따른' 탈락 금지)·여러 조문 나열 정리 시에도 각 항목 동일 유지·근거 법률 인용구를 옮긴 경우 답변 전 조문번호·연결어 누락 자가 점검 + ★over-blocking 차단 허용문 병기("요약·정리 자체는 허용"). 코드 로직·응답 schema·입력 스키마 무변 — `contract_version` **0.17.0 유지**, 패키지 patch bump(0.21.0 → **0.21.1**), 지원 규정 수 **52개 불변**·커넥터 재연결 불요. **선정·문구**: 계획 `/disc` 3-AI(Claude+Codex+Gemini) **3/3 GO 만장일치**(지시 1건만 최소형 — 백로그 표현 후보 2건[재구성 문구 강도·latest_history 라벨 출처 병기]은 2회 eval 연속 결함 0=트리거 0이라 동봉 기각·지시 과밀 회피) + 52규정 LIVE 현행성 전수 감사 전 건 일치(2026-07-22·data rider 0건) → 문구 `/disc` 3-AI 수정후 GO(수렴 2건 채택: 보존 대상 "인용구" 한정[개정문 전체 verbatim 강제로의 과확대 해석 차단]·'제N조에 따른' 예시화+자가 점검 대상 일반화[제N조의M·제N조제M항 변형 포괄]). **outage 회피**: 부팅/transport/검색 fan-out/공유 파서/캐시 완전 무접촉(프롬프트 문자열만).

### Changed

- **소비 가이드**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트 + `README.md` byte-sync): 근거 법률 인용 보존 지시 1문장을 위 3문장(보존 명문화·다중 항목 유지·자가 점검+허용문)으로 in-place 강화. 기존 잠금 문구("기관명만으로 축약하지 말고" 포함) 전부 보존 — v0.17.1 surface-consistency 테스트 무수정 통과(no-churn).

### Added

- **테스트 396 → 398**(`tests/test_tools.py`·`tests/test_b2_executor.py`·acceptance 가드 자동 +1): v0.21.1 surface-consistency(3표면 토큰 3종 — 원문 단위 그대로 보존·'제N조에 따른' 패턴·요약·정리 허용문)·패키지 0.21.1 잠금·신규 spec 구조 가드(파라미터화 자동 수집).
- **acceptance spec**(`tests/acceptance/v0_21_1.py`): Level A는 무회귀만(프롬프트-only라 응답 데이터 무변 — locate 스캔 블록·기본 경로 oversized_pointer·청크 verbatim·amendment 부착[law 일부개정·admrul 타법개정]·'연구개발비' returned ≥ 10 유지). 개선(조문번호 보존)은 Level-B 프롬프트(P4 재현·locate 라우팅 무회귀)로 배포 후 수동 eval.

### Deferred (scope 밖·backlog)

- 표현 후보 2건(재구성 표시 문구 강도·latest_history 라벨 출처 병기 — 트리거 0·백로그 유지)·별표 내 검색 v2·structured 목 parity·평면 admrul 항·호 파싱(C4)·R5/B3·annex_chunk/annex_locate 엄격 타입 검증·broad 드리프트.

## [0.21.0] - 2026-07-21

**대용량 별표 내 검색(opt-in) — 청크 다회 순회 비용 해소** — 배포 후 브라우저 라이브 eval 2회 연속(v0.20.0 P2·v0.20.1 P2)에서 호스트가 "별표들에 특정 문구(RCMS 등)가 있는가"류 부재 확인 질문에 `annex_chunk`를 7회 연속 호출해 수만 자를 전수 순회하는 실수요가 실측됐다(정답은 도달하나 호출·컨텍스트 비용 과다). `get_provision_detail`에 **optional 입력 `annex_locate`(문자열·기본 None)** 추가 — 별표(BP)+oversized일 때만 서버가 이미 확보한 별표 전문 텍스트를 줄 단위로 스캔하여 `annex_locate_result` 블록(`scanned_scope="annex_full_text"` 데이터 앵커·**전문 기준** `total_match_count`·매치 발췌[±1줄 원문 substring·표시 cap 6·`matches_truncated` 명시]·매치별 `chunk_index`[해당 구간 `annex_chunk` 재호출 안내])을 oversized_pointer 응답에 additive 부착한다. **0매치 = "서버가 별표 전문을 스캔한 결과 미발견"의 결정론 앵커** — v0.20.1 지시①(확인 범위 명시)을 호스트 자가 신고에서 서버 보장으로 상향하되, 스캔 한계(줄 단위 스캔이라 줄바꿈·표기 변형 미매치 가능·HWP 첨부 원문 범위 밖·부재 결론은 해당 별표 전문에 한정)를 `locate_note`에 동봉한다. 매칭은 search_provision의 토큰 규칙 재사용(의미토큰 2개+ 줄 내 토큰 AND·그 외 리터럴 — ★스코프는 줄 단위로 search_provision의 문서 전체 스코프보다 좁으며 locate_note가 이 한계를 고지) + 가운뎃점 유니코드 변형(ㆍ↔·) 정규화(v0.20.1 eval 실측 반영·발췌는 raw 원문) + 검색어 200자 상한(query echo가 응답 예산을 잠식하는 벡터 차단 — diff 적대검증 Codex 실측 반영). **추가 네트워크 0**. `contract_version` **0.16.0 → 0.17.0**(§5.18·입력 파라미터+응답 additive), 패키지 major bump(0.20.1 → **0.21.0**), 지원 규정 수 **52개 불변**. ★**입력 스키마 변경 릴리스**(v0.18.0·v0.20.0 이후 세 번째) — 배포 후 웹 커넥터 재연결(비활성→재활성) 안내·진행 중 세션은 구 tools/list 캐시라 신 파라미터 미노출. **선정·설계**: 52규정 LIVE 현행성 전수 감사 전 건 일치(data rider 0) + 코드 실측 → `/disc` 3-AI(Claude+Codex+Gemini) **3/3 GO 만장일치**(승격 게이트=실수요 2회 관측 충족·표현 patch 묶음 동봉=단일 의도 위반 기각·표시 cap 6 재사용·annex_chunk 동시 지정 시 청크 우선 2/3·regex/fuzzy 모드 과설계 기각). **outage 회피**: 기본(None) 경로·검색 fan-out·부팅/HTTP transport/health 완전 무접촉, 기존 포인터 `content`·`required_action`·청크 안내 문자열 무변(잠금 테스트 무수정 통과), 검색어 200자·excerpt 개별 400자 상한 + 직렬화 예산 방어 백스톱 2단(`matches_omitted`[스캔 결론 앵커 보존] → `annex_locate_omitted`[블록 통째 생략·airtight]).

### Added

- **`get_provision_detail` 입력 `annex_locate`**(optional str·기본 None): oversized 별표 한정 서버 측 전문 스캔. 문서레벨·조문(JO)·비-oversized 별표·빈 검색어에서는 무시 + 정직 경고 1줄(침묵 무시 방지·annex_chunk와 동형). `annex_chunk`와 동시 지정 시 청크 본문 조회 우선(locate 무시 + 경고).
- **`_annex_locate_result`·`_locate_normalize` 헬퍼**(`main.py`): 순수 함수·결정론. 매치 위치(첫 토큰 오프셋)→청크 경계 매핑으로 매치별 `chunk_index` 산출(청크는 원문 연속 substring이라 누적 길이가 곧 경계 — 문자 분할 초장문 줄에서도 정확)·매치 중심 발췌 윈도우(초장문 줄에서도 매치 문구가 발췌에 포함).
- **프롬프트 3표면 + README**(`_SERVER_INSTRUCTIONS`·docstring·`review_regulation` byte-sync): locate 라우팅("존재/부재 확인은 청크 전수 순회 전에 annex_locate 먼저")·0매치 소비(부재 근거 인용 허용 + 한계 표시)·발췌 부분성 오인 금지.
- **테스트 385 → 396**(`tests/test_tools.py`·`tests/test_b2_executor.py`·acceptance 가드): 매치/0매치 앵커·가운뎃점 정규화·토큰 AND·truncation·additive 잠금·우선순위/무시 경고·end-to-end·검색어 cap(query echo 예산 벡터)·megaline 매치 위치·surface-consistency(토큰 5종)·버전/contract 잠금.
- **acceptance spec**(`tests/acceptance/v0_21_0.py`): locate 실반환(law·admrul)·0매치 앵커·기본 경로 무회귀·검색 recall 무회귀 + Level-B 프롬프트(부재 확인 1-call 라우팅·과잉 단정 방지).

### Deferred (scope 밖·backlog)

- 표현 patch 묶음(재구성 표시 문구 강도·latest_history 라벨 출처 병기 — 단일 의도 분리)·structured 목 parity·평면 admrul 항·호 파싱(C4)·R5/B3·annex_chunk/annex_locate 엄격 타입 검증·broad 드리프트.

## [0.20.1] - 2026-07-21

**청크·이력 소비 표시 정밀화 — 별표 인용 방식·확인 범위 표시 + latest_history 마커 라벨 보존** — v0.20.0 배포 후 브라우저 라이브 eval(2026-07-20·CLEAN PASS·서버 결함 0)에서 관찰된 비차단 표현 리스크 2건을 예방적으로 완결하는 **프롬프트 문자열-only patch**(v0.17.1·v0.19.1과 동형). ① 호스트가 고정폭 박스 표 별표 청크 전문을 목록형으로 재구성(내용 무손실·"재구성" 고지·표본 오류 0)했으나 표시 규약이 없어, 향후 병합셀 복잡 표에서 왜곡이 "원문 인용"으로 위장될 잠재 리스크 → 별표 본문을 인용·정리해 표시할 때 **원문 줄 배열 유지 인용 / 내용 보존 재구성 / 일부 요약** 중 방식을 답변에 명시하고(★재구성·요약 자체는 허용 — 금지가 아니라 표시 요구·over-blocking 차단 허용문 병기), 별표 전체에 대한 결론(문구·수치 부재 판단 등)은 전체 청크 전수/일부 확인 범위를 명시하도록 지시. ② eval에서 latest_history '신설' 마커를 '손질'로 뭉뚱그린 사례(허용 요약 판정·허위 아님) → latest_history 값을 전달·요약할 때 마커 유형 라벨(개정·신설·삭제·본조신설 등)을 원문 라벨 그대로 표기하되, 기존 "유형에서 개정 범위·중요도를 추론 금지" 원칙과 분리 서술로 병립. 코드 로직·응답 schema·입력 스키마 무변 — `contract_version` **0.16.0 유지**, 패키지 patch bump(0.20.0 → **0.20.1**), 지원 규정 수 **52개 불변**·커넥터 재연결 불요. **선정·문구**: 패키지 선정 `/disc` 3-AI(Claude+Codex+Gemini) **3/3 GO**(별표 내 검색 locate=실수요 게이트 미충족·예방 코드=트리거 0·보류·규정 확대 전부 기각) + 52규정 LIVE 현행성 전수 감사 전 건 일치(2026-07-21·data rider 0건) → 문구 초안 `/disc` 3-AI 수정후 GO(수렴 3건 채택: 인용/재구성/요약 3분법·"latest_history 값을 전달할 때"로 한정·"내용 무손실"→"내용을 보존한"). **outage 회피**: 부팅/transport/검색 fan-out/공유 파서/캐시 완전 무접촉(프롬프트 문자열만).

### Changed

- **소비 가이드**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트 + `README.md` byte-sync): 위 2지시 삽입(청크 소비 지시 블록·latest_history 지시 블록 말미 append). 기존 잠금 문구 전부 무수정 보존(append/삽입만).

### Added

- **테스트**(`tests/test_tools.py`·`tests/test_b2_executor.py`): v0.20.1 surface-consistency(3표면 토큰 4종 — 방식 표시·재구성/요약 허용·확인 범위 표시·원문 라벨 보존)·패키지 0.20.1 잠금.
- **acceptance spec**(`tests/acceptance/v0_20_1.py`): Level A는 무회귀만(프롬프트-only라 응답 데이터 무변 — 청크 조회·oversized_pointer·amendment 부착·'연구개발비' returned ≥ 10 유지). 개선 2건은 Level-B 프롬프트(재구성 표시·전수 확인 범위 표시·마커 라벨 보존·over-blocking 확인)로 배포 후 수동 eval.

### Deferred (scope 밖·backlog)

- 서버 측 별표 내 검색/locate 보조 경로(실수요 관측 후)·annex_chunk 엄격 타입 검증·R5/B3·structured 목 parity·평면 admrul 항·호 파싱(C4)·broad 드리프트.

## [0.20.0] - 2026-07-20

**대용량 별표 본문 청크 조회(opt-in) — oversized 별표 접근성 해소** — v0.2.0 이래 대용량 별표(응답 예산 16,000자 초과)는 본문 전체 미수록(`oversized_pointer`·인용 금지)에 법제처 링크+검색 발췌(≤700자·매칭 행 cap 6)가 전부여서, 별표(단가·기준표·서식 위임)가 실질 데이터인 본 도메인에서 **호스트가 별표 본문을 도구로 읽을 수단이 구조적으로 전무**하던 한계를 해소한다(v0.19.1 eval P3에서 발췌 한계 hedge로 표면화). `get_provision_detail`에 **optional 입력 `annex_chunk`(기본 None)** 추가 — 별표(BP)+oversized일 때만 본문을 줄 경계 청크로 나눠 해당 청크를 **원문 그대로**(`plain_text_verbatim`·`verbatim_quote_allowed=true`) 반환한다. 청크는 원문 연속 substring(`"".join(chunks)==content` 무손실·결정론)이며 content에는 안내 마커를 섞지 않고(verbatim 순수성 — `/disc` Codex 수정 채택) 부분성 메타(`is_complete=false`·`chunk_index`·`chunk_count`·`total_char_count`·`chunk_note`)를 별도 필드로 동반한다. **추가 네트워크 0**(별표 본문은 상세조회 응답에 기존재). `contract_version` **0.15.0 → 0.16.0**(§5.17·입력 파라미터+응답 additive), 패키지 major bump(0.19.1 → **0.20.0**), 지원 규정 수 **52개 불변**. ★**입력 스키마 변경 릴리스**(v0.18.0 이후 두 번째) — 배포 후 웹 커넥터 재연결(비활성→재활성) 필요·진행 중 세션은 구 tools/list 캐시라 신 파라미터 미노출. **선정·설계**: `law-api-prober` LIVE 재확인 + 코드 실측 → `/disc` 3-AI(Claude+Codex+Gemini) **3/3 GO**(B 프롬프트-only 3연속·D 보류·발췌 예산 확대·전역 예산 상향 전부 기각 — 25k TOKEN 한도·전 경로 영향). **outage 회피**: 기본(None) 경로·검색 fan-out·부팅/HTTP transport/health 완전 무접촉, oversized_pointer 응답엔 `chunk_count`·재호출 안내만 additive(기존 content·required_action 문자열 무변), 사후주입 초과 백스톱(force_oversized)은 청크 요청도 포인터로 강등(airtight).

### Added

- **`get_provision_detail` 입력 `annex_chunk`**(optional int·기본 None): oversized 별표 한정 청크 조회. 범위 밖은 기존 오류코드 `not_found` + 유효 범위(1..chunk_count)·재호출 안내(신규 오류코드 0). 문서레벨·조문(JO)·비-oversized 별표에서는 무시 + 정직 경고 1줄(침묵 무시 방지).
- **`_annex_chunk_texts` 헬퍼**(`main.py`): `splitlines(keepends=True)` 세그먼트 greedy 결합 — 각 청크 JSON escaped 길이 ≤ 12,000(`_ANNEX_CHUNK_CONTENT_BUDGET`·최종 직렬화 16,000 예산에 ≥1k 여유). 예산 초과 단일 줄(정상 데이터 미관측)은 문자 단위 강제 분할로 진행 보장. 순수 함수(결정론) — 단 개정 시 경계 변동 가능하여 응답에 `effective_date` 앵커·경고 동반.
- **oversized_pointer 발견성**: 포인터 응답에 `chunk_count`·`chunk_note`(annex_chunk 재호출 안내)·경고 1줄 additive.
- **테스트**(`tests/test_tools.py`·`tests/test_b2_executor.py`): 청크 재조립 무손실·예산 상한·초장문 줄 폴백·청크 응답 부분성 메타·범위 밖 not_found·비-oversized/문서레벨/JO 정직 경고·기본 경로 무변 잠금·oversized 포인터 additive 잠금·surface-consistency(3표면 청크 라우팅 토큰)·contract 0.16.0/패키지 0.20.0 잠금.
- **acceptance spec**(`tests/acceptance/v0_20_0.py`): 혁신법 시행령 별표2(law:285767:BP0002) annex_chunk=1 청크 도달 + 기본 경로 oversized_pointer 무회귀 + admrul 대용량 별표 청크 + 무회귀 '연구개발비' returned ≥ 10. 청크 소비 품질(부분성 인지·발췌 미확인 라벨)은 Level-B 프롬프트로 배포 후 수동 eval.

### Changed

- **소비 가이드**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트 + `README.md` byte-sync): 대용량 별표 청크 라우팅(oversized_pointer → chunk_count 확인 → annex_chunk 재호출) + ★"검색 발췌·청크에 없는 문구·수치는 그 응답으로 확인된 것이 아니므로 확인 불가로 표시"(v0.19.1 eval 도출 발췌 한계 라벨 규칙을 신 기능 라우팅에 흡수). 기존 잠금 문구 전부 무수정 보존(append/신규 bullet만).
- **manifest 현행화**(`rule_sets.yaml` — 계약 외 데이터·직전 `/disc` 3/3 사전 승인 이연분 집행): 국토교통부소관 연구개발사업 운영규정 `api_doc_id` 2100000235502 → **2100000282288**·시행일 2024-01-22 → **2026-07-08**(타법개정·2026-07-20 LIVE 재확인: 정확 제목 일치 단 1행·조문 47·별표 3+별지 2·amendment 정상 파싱). 평시 실영향 0(search-first가 이미 신 문서 자동 채택) — fallback 정합성 정비.

### Deferred (scope 밖·backlog)

- 발췌 마커(`_annex_snippet`) 문자열 강화(검색 fan-out 표면 — 이번엔 무접촉 유지)·structured 목 parity·평면 admrul 항·호 파싱(C4)·R5/B3·JO(조문) 청크(대용량 조문은 v0.6.0 size-tier 유지 — 별표 대비 실수요 미관측).

## [0.19.1] - 2026-07-19

**eval 근본원인 프롬프트 가이드 보강 — 구체값 단정 금지 확장 + '개정 이력·연혁' 질의 라우팅** — v0.19.0 배포 후 브라우저 라이브 eval(2026-07-16·PASS_WITH_MINOR·서버 결함 0)에서 도출된 호스트 소비 품질 근본원인 2건을 해소하는 **프롬프트 문자열-only patch**(v0.17.1과 동형). ① P4(유일 minor): 호스트가 검증 조문 원문에 없는 "처리기한(예: 15일 이내 통보)" 임의 예시 구체값을 출력 — 기존 가드가 식별자(고시·예규 번호)만 커버하던 사각을 기한·금액·비율·수치 등 구체값(임의 예시 포함)으로 확장. ★over-blocking 방지를 위해 "도구 응답 원문에 있는 값은 그대로 인용" 허용문을 병기(인용 허용/금지 양립 — `/disc` 3-AI 반영). ② P3(관찰): "어떤 개정 이력이 있어?" 표현에 호스트가 MCP 미호출·웹-first — 라우팅 트리거를 '개정 이력'·'개정 내역'·'개정 경과'·'연혁' 등으로 확장하고, 본 서버는 최신 제·개정 1건만 제공(전체 연혁 목록 미제공)이라는 한계 고지 후 1차 출처 보강 분기 + amendment_kind="제정"이면 서버가 반환한 최신 제·개정구분 기준으로 제정 이후 개정 이력이 없다는 정합 지시를 명문화(무조건 도구 강제는 환각 위험으로 기각 유지). 코드 로직·응답 schema·입력 스키마 무변 — `contract_version` **0.15.0 유지**, 패키지 patch bump(0.19.0 → **0.19.1**), 지원 규정 수 **52개 불변**. **선정·문구**: read-only 에이전트 3개 실측(LIVE 52규정 전수 감사·프롬프트 4표면 census·backlog 6건 위험 평가) → 패키지 선정 `/disc` 3-AI 3/3 수정후 GO → 문구 초안 `/disc` 3-AI GO(Codex 수정 2건 채택: 트리거 표현 확장·"서버가 반환한 최신 제·개정구분 기준" 정밀화). **outage 회피**: 부팅/transport/검색 fan-out/공유 파서/캐시 완전 무접촉(프롬프트 문자열만).

### Changed

- **소비 가이드**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트 + `README.md` byte-sync): 위 2지시 삽입(표면당 ~350자). 기존 잠금 문구(식별자 단정 금지·부재≠무개정·clean diff 과장 금지 등) 전부 무수정 보존(append/신규 bullet만).

### Added

- **테스트**(`tests/test_tools.py`·`tests/test_b2_executor.py`): v0.19.1 surface-consistency(3표면 토큰 4종 — 인용 허용·임의 예시 금지·전체 연혁 미제공 고지·제정 정합)·패키지 0.19.1 잠금. 테스트 370 → **372**.
- **acceptance spec**(`tests/acceptance/v0_19_1.py`): Level A는 무회귀만(프롬프트-only라 응답 데이터 무변 — amendment_kind 부착·제정 skip·'연구개발비' returned ≥ 10 유지). 개선 2건은 Level-B 프롬프트(P4 재현·P3 재현·over-blocking 확인·기존 지시 무회귀)로 배포 후 수동 eval.

### Deferred (scope 밖·backlog)

- manifest fallback 현행화(국토부 운영규정 2100000235502→2100000282288 — 2026-07-19 LIVE 전수 감사에서 유일 CHANGED·평시 실영향 0[전 52건 resolve 성공]·차기 실질 릴리스에 동반, `/disc` 3/3)·structured 목 parity·평면 admrul 항·호 파싱(C4)·R5/B3.

## [0.19.0] - 2026-07-15

**admrul redline 확장 — 행정규칙 문서레벨 amendment_text·amendment_kind** — redline 테마(v0.17.0 amendment_text[law] → v0.17.1 소비 가이드 → v0.18.0 신구조문대비표 opt-in[law])가 law 트랙만 커버해, 행정규칙(고시·예규·훈령 — R&D 실무에서 개정이 가장 잦은 트랙)의 "이번 개정으로 무엇이 바뀌었나"에 서버가 아무 데이터도 못 주던 갭을 해소한다. `get_admin_rule_detail`이 `<개정문내용>`과 `<제개정구분명>`을 findtext로 캡처(추가 네트워크 0)해, **admrul 문서레벨 `get_provision_detail` 응답에도 `amendment_text`·`amendment_kind`를 additive 노출**한다(기존 law용 `_attach_amendment_meta` 헬퍼 무변경 재사용). ★admrul XML에는 law의 `<제개정구분>` 태그가 없어 `<제개정구분명>`을 `"제개정구분"` 키로 정규화 저장한다(태그명 함정 — LIVE 전수 실측). **입력 스키마 무변**(응답 additive만 — v0.18.0 같은 클라이언트 재연결 이슈 없음). `contract_version` **0.14.0 → 0.15.0**(§5.16·응답 schema 신규 출현), 패키지 **major** bump(contract bump = 큰 변화: 가운데 +1·마지막 0, 0.18.0 → **0.19.0**). 지원 규정 수 **52개 불변**. **선정·검증**: `law-api-prober` LIVE 전수(admrul 23건 — 존재 15/부재 8[태그 자체 부재·결정론]·최대 3,836자·제개정구분명 전건 존재·이스케이프/`<img>` 0) → `/disc` 3-AI(Claude+Codex+Gemini) 3/3 GO(제정 skip 유지·태그 정규화 위치·제개정구분코드 제외·게이트 분리 전부 합의). **outage 회피**: 부팅/HTTP transport/health/캐시-bootstrap·검색 매칭/랭킹/fallback/fan-out 예산 비의존(검색 fan-out 공유 파서 접촉은 never-raise findtext 2건뿐 — v0.15.0 조문참고자료 선례와 동형·검색은 신규 필드 미소비라 blast radius 0)·whole-or-omit(articles 100% 보호)·롤백 먼저.

### Added

- **`live_api.get_admin_rule_detail`**: `<개정문내용>`(`.//개정문내용` — LIVE 전수 실측상 전건 `<개정문>` wrapper 아래 단일 text node·복수 출현 0) + `<제개정구분명>`(값 "일부개정" 18·"제정" 4·"전부개정" 1 — `"제개정구분"` 키로 정규화·`<제개정구분코드>`는 소비 가치 없어 미캡처) findtext 캡처. 부재 시 빈 문자열(태그 자체 부재 = 결정론·never-raise).
- **admrul 문서레벨 `amendment_text`·`amendment_kind`**(`main.py`): 부착 게이트를 law 한정에서 law+admrul 문서레벨로 완화(★amendment 게이트와 `include_old_and_new` 게이트는 분리 유지 — oldAndNew API가 admrul 미지원이므로 오호출 원천 차단). 제정 skip 유지: admrul 제정 4건은 개정문이 실재하나(law와 달리) 내용이 발령 헤더+"[본문 생략]"+부칙 등 발령 메타(개정 delta 아님·LIVE 실측)라 skip으로 amendment_text 의미를 양 트랙 동일 보존. whole-or-omit(articles 백스톱 이후 부착·초과 시 통째 생략+`amendment_text_omitted`) 그대로 — admrul 개정문 최대 3,836자라 생략 발동 가능성 낮음.
- **테스트**(`tests/test_tools.py`·`tests/test_b2_executor.py`): admrul 문서레벨 부착·제정 skip·부재 graceful(kind만 부착)·oversized 통째 생략·제개정구분명 정규화 파싱(live_api 2종)·admrul opt-in 시 oldAndNew 미호출(게이트 분리 잠금)·admrul 조문(JO) 상세 미부착 잠금(문서레벨 한정 — diff 적대검증 반영)·surface-consistency(3표면 admrul 확장·부재≠무개정 토큰·구 "law 한정" 문구 잔존 금지)·contract 0.15.0/패키지 0.19.0 잠금. 테스트 360 → **370**.
- **acceptance spec**(`tests/acceptance/v0_19_0.py`): 시설장비 표준지침(개정문 최대 건) amendment_text 부착·연구개발비 사용 기준 kind=일부개정+text 부재(부재≠무개정 데이터 앵커)·law 무회귀(혁신법 amendment_kind 유지)·무회귀 '연구개발비' returned ≥ 10.

### Changed

- **소비 가이드**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트 + `README.md` byte-sync): amendment_text·amendment_kind 안내를 "law 한정"에서 law·admrul 양 트랙으로 갱신 + ★행정규칙은 개정문이 제공되지 않는 문서가 있어(일부개정인데도 부재 실재) **amendment_text 부재를 무개정으로 단정 금지** 지시 추가. 기존 v0.17.x amendment framing(전수 열거·citation 보존·전신 연혁 단정 금지·clean diff 과장 금지) 보존.

### Deferred (scope 밖·backlog)

- structured 목 parity·평면 admrul 항·호 정규식 파싱(C4)·R5 길이상한/B3 연결풀·`제개정구분코드` 노출·admrul용 신구조문대비표(oldAndNew API 자체가 admrul 미지원 — 불가).

## [0.18.0] - 2026-07-14

**형태 B redline — 신구조문대비표(oldAndNew) opt-in 노출 (law 한정)** — redline 테마(v0.14 가지조문 → v0.15 조문 개정이력 → v0.16 검색 경로 → v0.17.0 amendment_text 개정지시문 산문 → v0.17.1 소비 가이드)의 다음 단계로, v0.16.0 eval에서 관측된 "무엇이 바뀌었나"(개정 전/후 원문 대조) 수요의 마지막 조각을 해소한다. 국가법령정보 OpenAPI의 신구조문대비표(`lawService.do?target=oldAndNew` — 개정 전/후 조문 원문 2열)를 `get_provision_detail`의 **optional 파라미터 `include_old_and_new`(기본 false)** 로 노출: true + law 문서레벨일 때만 **+1 요청**으로 조회해 `old_and_new` 블록(old/new 데이터 앵커·rows 2열 verbatim)을 additive 부착한다. **기본(false) 경로·검색 fan-out·부팅/transport 완전 무접촉**(outage 격리). `contract_version` **0.13.0 → 0.14.0**(§5.15·입력 파라미터+응답 schema 신규 필드), 패키지 **major** bump(contract bump = 큰 변화: 가운데 +1·마지막 0, 0.17.1 → **0.18.0**). 지원 규정 수 **52개 불변**. **선정·설계**: 배포 전 `law-api-prober` LIVE 실측(law 29건 전수 sweep — 대비표 실재 23/29·결정론 부재 신호 `신구법존재여부=N`·최대 26,553자·★일부개정인데 부재 2건[286879·262117]·★검색 변형 `lawSearch`는 응답에 OC 키 원문 포함이라 사용 금지) → `/disc` 3-AI(Claude+Codex+Gemini) 3/3 GO(설계 3안 중 opt-in 파라미터 채택 — 항상 부착은 전 문서레벨 +1 네트워크·크기 압박, 신규 도구는 표면 파편화; 조문별 그룹핑은 파서 위험·scope 증가로 기각). **outage 회피**: opt-in 격리·never-raise(조회 실패 시 `old_and_new`만 fetch_failed·본문 응답 정상)·whole-or-omit 3단(절단 금지)·전용 캐시 분리(detail warm-hit 무간섭)·롤백 먼저.

### Added

- **`live_api.get_old_and_new`**: `lawService.do?target=oldAndNew&MST=` XML 파싱 — 구/신 기본정보(공포일자·공포번호·시행일자·현행여부) + 구조문목록/신조문목록(`<조문 no=N>` 평면 행·no 순번 정렬·양측 행 수 동일 실측). 부재는 `신구법존재여부=N`/목록 부재로 결정론 판별(`available: false`). 빈 body(HTTP 200) 1회 재조회 방어(LIVE 프로브 1회 관측). ★`lawSearch.do?target=oldAndNew` 사용 금지(응답 `신구법상세링크`에 OC 인증키 원문 포함 — LIVE 실측). 전용 `_old_and_new_cache`(maxsize 16·ttl 24h)로 `_detail_cache`(fan-out warm-hit) 간섭 차단.
- **`get_provision_detail(provision_id, include_old_and_new=false)`** + **`_attach_old_and_new` 헬퍼**(`main.py`): true + law 문서레벨일 때만 `old_and_new` 블록 부착 — `available`·`basis`(★직전 공포 연혁 대비·현행 대비 아님 — 구조문이 미시행 분리시행분일 수 있어 old/new 날짜·현행여부 데이터 앵커로 방어)·`markers_note`(`<P>` 변경 하이라이트·"(생  략)"/"(현행과 같음)" 무변경 축약·"<신  설>" placeholder)·`old`/`new`(doc_id·공포일자·공포번호·시행일자·현행여부)·`rows`(no 순번 2열 pair·verbatim·조문별 그룹핑 없음). `available=false`는 `reason`으로 구분: `not_provided`(★부재 ≠ 무개정 — 일부개정인데 부재인 문서 실재를 note에 데이터 앵커로 명시) / `fetch_failed`(never-raise — 본문 응답 정상 유지). 크기는 whole-or-omit 3단: 예산(16,000) 내 전체 부착 → `rows`만 통째 생략(`rows_omitted`·메타 앵커 유지) → 블록 제거+`old_and_new_omitted` 플래그. articles·amendment_text는 100% 보호(최하위 우선순위 부착). unit(JO/BP) 조회에서는 무시, admrul 문서레벨은 미지원 정직 경고 1줄(네트워크 미발생).
- **테스트**(`tests/test_tools.py`·`tests/test_b2_executor.py`): opt-in 부착(2열 pairing·데이터 앵커)·기본 false 미조회(네트워크 0)·not_provided 정직 note·fetch_failed never-raise·oversized rows 생략(articles 보존·최종 직렬화 예산 내)·행 수 불일치 min-zip·admrul 경고·JO 무시·live_api 파서(2열 정렬·부재 플래그·빈 body 재조회)·surface-consistency(3표면 소비 가이드 토큰)·contract 0.14.0/패키지 0.18.0 잠금.
- **acceptance spec**(`tests/acceptance/v0_18_0.py`): 중기법(281987) opt-in 대비표 available·제정 시행령(282915) not_provided·기본 경로 무회귀(amendment_kind 유지)·무회귀 '연구개발비' returned ≥ 10. Level-B(호스트 2열 대조 소비·부재 정직 안내)는 배포 후 수동 eval 프롬프트로 출력.

### Changed

- **소비 가이드**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트 + `README.md` byte-sync): 개정 전/후 조문 원문 2열 대조가 필요하면 law 문서레벨에 `include_old_and_new=true` 지정 → `old_and_new` 확인. ★직전 공포 연혁 대비(현행 대비 아님)·마커 의미(`<P>`/"(생 략)"/"(현행과 같음)"/"<신 설>")·부재(available=false) ≠ 무개정·`rows_omitted` 시 `document_source_url` 확인. 기존 v0.17.0~0.17.1 amendment framing 보존.

### Deferred (scope 밖·backlog)

- 조문별 그룹핑("제N조" 접두 재구성)·조문별 선별 반환·과거 연혁 MST 지정(특정 개정분 대비표)·admrul redline 확장(개정문 15/23·별도 파서 2경로)·structured 목 parity.

## [0.17.1] - 2026-07-13

**개정 전/후 대조(redline) 소비 품질 프롬프트 보강 — v0.17.0 eval host-side minor 3건 대응** — v0.17.0 배포 후 브라우저 라이브 eval(claude.ai·Sonnet 4.6)에서 기능은 end-to-end 작동(fabrication 0)했으나 호스트 LLM의 amendment_text 소비 행동에서 minor 3건이 관찰됐다(모두 서버 데이터는 완전·순수 소비 품질 문제): (1) 개정문 개정항목 6개 중 5개만 다루고 가지조문(제27조의2제2항)을 통째 누락(선택적 초점), (2) 제정 법령 답변에서 도구 미검증 전신 법령명·연혁을 단정 서술, (3) 개정후 대체문 인용 시 근거 법률 인용(법명·조문 번호)을 기관명 요약으로 탈락. 세 실패 모두 **서버 코드 결함이 아니라 amendment 소비 가이드 공백**이라, 프롬프트 표면 3곳(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트[README byte-sync])에 동일 취지 3지시를 **기존 amendment 문단 내 최소 증분으로 삽입**(새 섹션 append 아님)하여 대응한다. **코드 로직 무변경·순수 프롬프트 문자열 상수 교체** → `contract_version` **0.13.0 유지**·응답 schema/필드/shape 불변·패키지 **patch** bump(0.17.0 → **0.17.1**). 지원 규정 수 **52개 불변**. **선정·검증**: 차기 패키지 선정 `/disc` 3-AI 3/3 "수정 후 GO"(형태 B redline·admrul 확장 등 backlog는 신규 네트워크·파서 동반 = 중위험이라 이번 최소·안전 patch 후순위) → 문구 초안 `/disc` 3-AI 3/3 "수정 후 GO"(문구 정제 3건 채택: "명시된 항목만" 앵커·"기관명만으로 축약하지 말고"·"도구 응답으로 확인되지 않은"; scope creep 1건[용어 치환 금지] 기각). **outage 회피**: 부팅/HTTP transport/health/미들웨어/검색 fan-out 전부 무접촉(문자열 상수만 변경).

### Changed

- **amendment 소비 가이드 3지시 추가**(`main.py` `_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`_REVIEW_PROMPT_TEMPLATE` + `README.md` byte-sync): ① 개정 전/후 정리 시 amendment_text에 명시된 개정 지시 항목을 가지조문(제N조의M) 포함 빠짐없이 점검·분량상 줄일 때는 다룬 범위·생략 항목 명시(임의 누락 금지) ② 개정후 대체문 인용 시 근거 법률 인용(법명·조문 번호)을 기관명만으로 축약 금지·보존 ③ 제정·타법개정 배경으로 도구 응답 미확인 전신 법령명·연혁 단정 금지(추정 표시 또는 생략). 기존 "clean diff 과장 금지" 가드 등 v0.17.0 framing 보존.

### Added

- **테스트**(`tests/test_tools.py`): surface-consistency 회귀 — 3지시 핵심 토큰이 3개 프롬프트 표면 전부에 존재하고 "clean diff 과장 금지" 가드가 보존됐는지 공백 정규화 후 검증. 패키지 0.17.1 잠금.
- **acceptance spec**(`tests/acceptance/v0_17_1.py`): 무회귀 '연구개발비' returned ≥ 10(프롬프트 변경은 응답 데이터 무변). Level-B(호스트 소비 행동) 3건은 자동 검증 불가라 배포 후 수동 eval 프롬프트로 출력(redline 전수 열거·제정 연혁 자제·citation 보존). 테스트 345 → **347**(surface-consistency +1·acceptance spec parametrize +1).

## [0.17.0] - 2026-07-09

**개정 전/후 대조(redline) 최소형 — 문서레벨 amendment_text·amendment_kind** — 개정 발견성 테마(v0.14 가지조문 → v0.15 조문 개정이력 → v0.16 검색 경로 개정이력)의 자연 후속. v0.16.0 배포 후 브라우저 라이브 eval에서, 호스트가 "어느 조문이 개정됐나"를 1턴에 풀게 되자 곧이어 "그래서 **무엇이** 바뀌었나"(개정 전/후)를 물었는데 도구가 현행 원문+마커만 주고 diff를 못 줘 2회 아쉬워한 관찰을 해소한다. `live_api.get_law_detail`이 이미 받아오지만 버리던 `<개정문내용>`(개정지시문 산문·"'출연'을 '지원'으로 한다" 식 실질 delta)과 `<제개정구분>`을 findtext(never-raise)로 캡처해, **law 문서레벨 `get_provision_detail` 응답에 `amendment_text`·`amendment_kind`를 additive 노출**한다(**추가 네트워크 0** — 이미 fetch하는 XML 안에 있음). `contract_version` **0.12.0 → 0.13.0**(§5.14·응답 schema 신규 필드), 패키지 **major** bump(contract bump = 큰 변화: 가운데 +1·마지막 0, 0.16.0 → **0.17.0**). 지원 규정 수 **52개 불변**. **선정·검증**: ultracode 워크플로 12에이전트(dossier 8종 + 3렌즈 + 종합)가 redline 데이터 미확정으로 처음엔 defer했으나, `law-api-prober` LIVE census가 경량 실현(형태 A)을 확인 → `/disc` 3-AI(Claude+Codex+Gemini) R1 만장일치 R 채택 → LIVE 정밀 census(law 29 전건 + admrul 23 전수) → `/disc` R2 3-AI로 edge 4건 확정. **size 안전**: whole-or-omit(절단 금지=false-completeness 방지)·기존 articles 백스톱 이후 opportunistic 부착으로 **articles(v0.7.0 발견성) 100% 보호**. **outage 회피**: 부팅/HTTP transport/health/캐시-bootstrap·검색 매칭/랭킹/fallback/fan-out 예산 비의존(get_law_detail findtext + 문서레벨 응답 build만 변경)·검색 fan-out은 신규 필드 미소비(blast radius 0)·롤백 먼저.

### Added

- **개정문 필드 캡처**(`live_api.py` `get_law_detail`): 응답 root의 `<개정문내용>`·`<제개정구분>`을 findtext로 캡처(never-raise·검색 fan-out 공유 경로 안전 — 이 필드는 search가 소비하지 않아 blast radius 0). LIVE census: 단일 element·자식 0·HTML 이스케이프 0(unescape 불요).
- **`_attach_amendment_meta` 헬퍼 + law 문서레벨 부착**(`main.py`): `amendment_kind`(제개정구분·해석 가드)·`amendment_text`(개정문). ★`amendment_kind=="제정"`이면 amendment_text skip(census: 제정건 blob 정체=서명부+부칙·redline 가치 낮음). ★whole-or-omit — articles 백스톱 *이후* 실 `json.dumps` 측정으로 예산(16,000) 내면 부착·초과 시 통째 생략 + `amendment_text_omitted`(+가능 시 경고·`document_source_url` 포인터). law 트랙 한정(호출부 `pid.doc_type=="law"` 게이트). verbatim 노출(별지 서식 개정 `<img>` 참조 태그 포함 가능·정규식 제거는 원문 훼손 위험이라 미적용).
- **테스트**(`tests/test_tools.py`): law 문서레벨 amendment_text·amendment_kind 부착·제정 skip·admrul 문서레벨 미부착(law-only 게이트)·oversized base 통째 생략(amendment_text_omitted·articles 보존)·필드 부재 graceful. contract 0.13.0/패키지 0.17.0 잠금. 테스트 339 → **345**.
- **acceptance spec**(`tests/acceptance/v0_17_0.py`): law 문서레벨 amendment_text·amendment_kind 존재(일부개정 규정)·제정 규정 amendment_text 부재·산업기술 시행령(285891) 생략 경로·무회귀 '연구개발비' returned ≥ 10.

### Changed

- **정직 framing**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트·README byte-sync): "이번 개정으로 무엇이 바뀌었나"는 문서레벨 `amendment_text`로 답하되 최신 개정분의 원 개정문 산문이지 조문별 완전 대조(clean diff)가 아니므로 과장 금지·`amendment_kind=="제정"`은 전체 신설·`amendment_text_omitted`/부재 시 `document_source_url` 확인·law 한정.

### Deferred (scope 밖·backlog)

- 형태 B(신구조문대비표 `target=oldAndNew` 구조화 2열 diff·신규 네트워크+파서)·조문별 slice·과거 개정 이력·`amendment_reason`(제개정이유)·admrul redline 확장(개정문 15/23만 보유·별도 파서 2경로).

## [0.16.0] - 2026-07-08

**검색 경로 개정 이력 발견성 노출 — search_provision/suggest 결과의 law 조문에 latest_history** — 직전 v0.15.0이 조문 개정 이력(공포일) `latest_history`를 **문서 레벨 조회 전용**으로 넣었으나, 배포 후 브라우저 라이브 eval(claude.ai·Sonnet 5 High) **발견 #1**: 호스트의 "최근 개정 조문?" 기본 본능이 키워드 검색(`search_provision`)이라, 문서레벨 전용 신호를 1턴에 만나지 못하고 사용자 nudge 후 2턴에야 문서레벨 순회로 정답 도달. 검색 경로(검색 결과·추천 후보)에 개정 신호가 0이었다. 이를 `search_provision` 결과의 **law 조문(article) 매치에 `latest_history`를 additive 노출**(v0.15.0 §5.12와 동일 값·헬퍼)하여 검색-first 경로에서 개정 신호를 결정론 데이터로 즉시 인지하게 해소한다(데이터 앵커 > 프롬프트, v0.5.0 원칙). `suggest_review_sources`가 검색 결과 dict를 그대로 복사(`dict(m)`)해 후보를 구성하므로 이 필드가 **추천 후보에도 자동 전파**된다(코드 확인). `contract_version` **0.11.0 → 0.12.0**(§5.13·응답 schema 신규 필드), 패키지 **major** bump(contract bump = 큰 변화: 가운데 +1·마지막 0, 0.15.0 → **0.16.0**·최근 규칙 패턴 contract bump ⟺ major 정합). 지원 규정 수 **52개 불변**. **최소형(leg1 단독)** — 개정 의도 질의 유도 note·`document_provision_id` 노출 두 leg은 **`/disc` 3-AI(Claude+Codex+Gemini) R1 만장일치로 gold-plating 판정·드롭**(note는 이미 있는 서버 안내와 동일한 Level-B 프롬프트 레버라 중복 + base_size 산입 복잡도 위험 / `document_provision_id`는 매치 `provision_id`에서 파생 가능·응답 크기 지배 항·scope creep → backlog 이월). **outage 회피**: 부팅/HTTP transport/health/캐시-bootstrap·파서(live_api)·검색 매칭/랭킹/fallback/fan-out 예산 비의존(응답 build만 변경)·`_article_amendment_history` never-raise 재사용(추가 네트워크 0·CPU regex만)·16k char 예산 내 뒤쪽 절단(응답 초과·크래시 구조상 불가)·롤백 먼저.

### Added

- **`latest_history` 검색 노출**(`main.py` `search_provision` article emit 분기): law 조문 매치에 `_article_amendment_history(art)` 값이 있으면 `latest_history`(예 `"개정 2025.12.30(공포)"`) additive 부착. `rs.api_target == LAW` 한정(평면 admrul·별표 매치는 조문참고자료 미보유라 None → 필드 생략)·마커 부재 시 생략·`_build_match` 내부가 아니라 article 분기에서만 부착(별표 경로 오염 원천 차단). `suggest_review_sources` 후보에 자동 전파(shallow copy).
- **테스트**(`tests/test_tools.py`): law 조문 매치 부착·admrul/별표 매치 생략·마커 부재 생략·suggest 후보 전파·검색 응답 허용키 집합에 `latest_history` 추가·contract 0.12.0/패키지 0.16.0 잠금. 테스트 334 → **339**.
- **acceptance spec**(`tests/acceptance/v0_16_0.py`): '개정' 질의에서 law 조문 매치에 `latest_history` 부착 존재·무회귀 '연구개발비' returned ≥ 10·중기법 도달. Level B에 v0.15.0 발견 #1 그 질의(중기법 "2026 개정 조문") before/after 검증 프롬프트.

### Changed

- **정직 framing**(`_SERVER_INSTRUCTIONS`·`search_provision`/`review_regulation` docstring·프롬프트·README byte-sync): 검색·추천 결과의 `latest_history`는 키워드에 걸린 조문에 한정되므로 개정 조문 **전수** 확인은 문서레벨 `articles` 목록을 사용하도록 명시. 날짜=공포일(값에 (공포) 표기·시행일 아님)·유형은 마커 유형·필드 부재 ≠ 미개정 보증은 v0.15.0 문구 재사용.
- `contract_version` **0.11.0 → 0.12.0**(§5.13). `docs/api_contract.md` §5.13 신설·변경 이력 표 행 추가.

### Deferred (backlog)

- **개정 의도 질의 유도 top-level note** — 배포 후 eval에서 "검색 `latest_history`는 봤으나 문서레벨 전수 이동 실패"가 재현되면 후속 소형 릴리스로 재상정.
- **`document_provision_id` per-match 노출** — 발견성 대비 응답 크기 비용·`provision_id` 파생 가능성으로 드롭.

## [0.15.0] - 2026-07-08

**law 조문 개정 이력(공포일) 발견성 — 문서 레벨 개정 힌트** — 특정 법령의 "최근 개정된 조문"을 조문 목록 레벨에서 발견 가능하게 한다. 종전에는 조문 개정 마커(`<개정 2025.12.30>` 등)가 조문 content 안에만 있어 개별 조문을 하나씩 열어야만 보였다(닭-달걀: 어느 조문이 개정됐는지 모르면 열 조문을 고를 수 없음). v0.13.1 라이브 eval **shortfall A**에서 「중소기업 기술혁신 촉진법」(MST 281987)이 2026-07-01 시행 개정(제10조 융자 지원 도입·제18조③ SW 사용료 지원 신설)됐는데도 호스트가 제15·31조만 조회한 뒤 "법률 2026 개정 확인 안 됨"으로 **false-negative** 결론을 낸 결함을 직접 겨냥한다. document-level `articles` 목록의 각 조문 항목과 `get_provision_detail`(JO) 상세에, 그 조문의 최신 이력 마커 `latest_history`(예 `"개정 2025.12.30(공포)"`·`"본조신설 2026.6.30(공포)"`·`"삭제 2020.3.3(공포)"`)를 additive로 노출한다(마커 없으면 필드 생략). `contract_version` **0.10.0 → 0.11.0**(응답 schema 신규 필드), 패키지 **major** bump(시스템 전역 신규 조회 유형 + contract bump = 큰 변화: 가운데 숫자 +1·마지막 0, 0.14.0 → **0.15.0**). 지원 규정 수 **52개 불변**. **law 트랙 한정**(admrul 평면 schema는 조문별 개정 마커가 없어 — LIVE census 확정 — 전건 미부착). **`/disc` 3-AI(Claude+Codex+Gemini) R1 3/3 GO·blocking 0**(후보 A 만장일치·조문시행일자 필드 reject[문서 시행일 echo·혁신법은 미래 분리시행일 오염]·조문변경여부 비노출[비공식 귀납·직전 공포 1건 한정]·content+조문참고자료 병행 소스[신설 조문은 참고자료가 유일 소스]·최소형 표면 합의). **law 29문서 전수 census(law-api-prober LIVE)가 구현을 1건 교정**: 조문참고자료에서 임의 날짜 loose-grab이 `[법률 제16892호(2020.1.29) …개정…]` 타법 개정 참조의 날짜를 이 조문 이력으로 오추출 → **접두 라벨 anchored 추출만**으로 폐쇄(이동 재번호도 함께 배제). **outage 회피**: 부팅/HTTP transport/health/캐시-bootstrap 비의존(도구 응답 build만 변경)·doc-level 집계는 검색 fan-out과 미공유 요청격리 경로(검색 latency 0)·신규 파서/추출 코드 never-raise(fault-isolation)·롤백 먼저.

### Added

- **`latest_history` 필드**(`main.py`): document-level `articles` 목록 항목·`get_provision_detail`(JO) 상세에 조문별 최신 이력 힌트 `"{유형} {공포일}"` additive(마커 부재 시 생략). 신규 추출 헬퍼 `_article_amendment_history` — content 꺾쇠 마커(개정/신설/삭제)와 `조문참고자료` 대괄호 마커(본조신설/전문개정/제목개정)의 최신 공포일 도출. never-raise·원문 verbatim(공백만 정규화·fabrication 0)·동일 날짜 tie-break는 content 실텍스트 마커 우선.
- **`조문참고자료` 파서 캡처**(`live_api.py`): `get_law_detail`·`get_admin_rule_detail` 중첩 파서에 `조문참고자료` findtext 추가(never-raise) — 신설 조문(제N조의M)은 content 마커가 없고 `[본조신설 …]`이 이 태그에만 있어 캡처 필수.
- **테스트 7건**(`tests/test_tools.py`): content 마커(개정/신설/삭제 라벨·다중 날짜 최신값)·조문참고자료 라벨 anchored(★타법 참조 날짜 미추출·이동 배제·본조신설)·content 우선 tie-break·★never-raise(비정상 입력 전건)·doc-level `latest_history` 부착/생략·JO 상세 동반·파서 조문참고자료 캡처. 테스트 326 → **334**.
- **acceptance spec**(`tests/acceptance/v0_15_0.py`): 중기법 제10·18조 이력 힌트 도달(=shortfall A 재현)·신설 가지조문 제7조의2 `본조신설` + 광역 무회귀. Level B에 shortfall A 그 질의 before/after·호스트 오독(필드 부재→미개정 단정) 검증 프롬프트.

### Changed

- **정직 framing**(`_SERVER_INSTRUCTIONS`·`get_provision_detail` docstring·`review_regulation` 프롬프트·README byte-sync): "최근 개정 조문"은 doc-level `articles`의 `latest_history`로 발견하되 — 날짜=**공포일**(시행일 아님)·유형은 마커 유형일 뿐 개정 범위·중요도 아님·**필드 부재 ≠ 미개정 보증**(마커 미캡처일 수 있음)을 명시(신규 false-negative 차단).
- **명시적 reject**: `조문시행일자`(문서 시행일 echo — 혁신법 283849는 전 조문에 미래 분리시행일 20260911이 찍혀 "이 조문 개정 시행일"로 쓰면 오답)·`조문변경여부`(비공식 귀납·직전 공포 1건만 표시) 두 구조화 필드는 노출하지 않음(LIVE census 근거).
- **문서**: `docs/api_contract.md` §5.12 신설(개정 이력 발견성)·contract 0.11.0 버전 이력 행 추가.

## [0.14.0] - 2026-07-07

**가지조문(제N조의M) 조회·발견 지원** — 국가법령정보 OpenAPI의 가지조문(제7조의2 등 "제N조의M" 형태로 개정에서 신설·추가되는 조문)을 검색·문서레벨 목록·상세조회로 지원한다. 종전에는 provision_id의 JO(조문) 식별자가 숫자만 지원해 파서가 가지조문을 침묵 skip했다(제N조와 제N조의M이 같은 JO 번호로 충돌). v0.13.1 라이브 eval에서 「중소기업 기술혁신 촉진법 시행령」(MST 287505)의 2026.6.30 개정 핵심 신설 조문 **제7조의2(융자·보증 지원기관)·제8조의2(융자·보증 대상·조건·절차)가 가지조문이라 도구가 반환하지 못한** user-facing 결함을 직접 겨냥(system-wide: law manifest 29개 문서에 181개 가지조문 전건 미반환·정수 조문 대비 약 19% 커버리지 갭). 이미 shipped된 **가지별표 BP 6자리 인코딩**(v0.2.1) 패턴을 조문(JO)에 정확히 미러한다. `contract_version` **0.9.0 → 0.10.0**(provision_id 포맷 확장 + 검색/doc-level/상세 응답에 가지조문 유입·거동 변경), 패키지 **major** bump(시스템 전역 신규 조회 유형 + contract bump = 큰 변화: 가운데 숫자 +1·마지막 0, 0.13.1 → **0.14.0**). 지원 규정 수 **52개 불변**. 단일 의도(가지조문 지원)로 한정 — C4 평면 admrul 항·호 structured 분해·개정 조문 발견성·목 structured parity는 동승하지 않음. **`/disc` 3-AI(Claude+Codex+Gemini) R1이 워크플로 권고를 2건 교정**: ① carve(검색 emit 제외) → full C1(검색 포함)로 만장일치 교정(검색이 주 발견 경로라 carve는 false economy) ② 협소화 정규식이 6자리 가지 00을 재-aliasing하는 결함 발견 → 가지 01~99만 허용. **구현 diff 적대검증(`/goal-disc-out` Codex+Gemini)이 2건 추가 교정**: ③ `rule_sets.yaml` `known_limitations` 41건의 stale "가지조문 누락 가능/표현 불가" 경고 제거(도구가 제7조의2를 반환하면서 동시에 "누락 가능"을 경고하던 자기모순 해소) ④ `_article_branch_no` 강건화(초장문 가지번호 `int()` raise 방지 length 가드 + 비정수 가지 → None skip으로 본조문 id aliasing 취약점 폐쇄). **outage 회피**: 부팅/HTTP transport/health/캐시-bootstrap 비의존(도구 응답 build만 변경)·신규 파서 코드 never-raise(fault-isolation)·롤백 먼저.

### Added

- **가지조문 JO 6자리 인코딩**(`provision_id.py`): `unit_id`가 `JO{번호4}{가지2}` 6자리로 가지조문 표현(예 `JO000702`=제7조의2·가지별표 BP 6자리 동형)·`unit_label`이 "제7조의2" 디코드. 본조문은 종전대로 `JO{번호4}` 4자리(불변·하위호환).
- **공유 헬퍼**(`main.py`): `_article_unit_id`/`_article_branch_no`(별표 `_annex_unit_id`/`_annex_branch_no` 미러) — 검색 emit·document-level `articles` 목록·`get_provision_detail`(JO) 상세가 단일 인코딩/판정을 공유(죽은 id 방지). 조문번호 비ASCII·비숫자·인코딩 불가(≥5자리 조문번호·≥3자리 가지)는 `None`으로 방어적 skip(never-raise).
- **테스트 10건**(`tests/`): (provision_id 4) JO 6자리 가지 파싱·라벨·가지 00 reject·5/7자리 reject / (파서·도구 6) 중첩 law 파서 가지조문 캡처·평면 admrul `_parse_flat_article` 가지 캡처·`_article_unit_id` 방어적 skip·doc-level 가지조문 공존(제7조/제7조의2/제8조의2 distinct id)·검색 6자리 JO emit·상세 (번호,가지) 엄격 매칭(제7조↔제7조의2 오도달 0). + acceptance spec 무결성 가드 파라미터 1건(자동 발견). 테스트 315 → **326**.
- **acceptance spec**(`tests/acceptance/v0_14_0.py`): 가지조문 도달(sme_tech_decree 제7조의2·제8조의2 검색 '융자 보증' + `law:287505:JO000702` 상세 unit_id 에코·not_found 부재) + 광역 '연구개발비' 무회귀. Level B에 최근 개정 가지조문 grounding(v0.13.1 eval 재현)·무회귀 프롬프트.

### Changed

- **`_UNIT_PATTERN` 협소화**(`provision_id.py`): JO를 종전 `JO\d{4,}`(4자리 이상 무제한)에서 `JO\d{4}(?:0[1-9]|[1-9]\d)?`(4자리 본조문 / 6자리 가지·가지 01~99)로 협소화. 종전 무제한은 6자리 `JO000602`를 이미 통과시켜 "제602조"로 오해석(collision-safety latent 결함) — 6자리 가지 emit 전 폐쇄가 전제. 서버 emit 이력은 전건 정확 4자리라 실 blast 0. BP는 v0.2.1 선례 보존(협소화 대상 아님).
- **파서 3경로 가지조문 포함**(`live_api.py`): `get_law_detail`·`get_admin_rule_detail`·`_parse_flat_article`에서 가지조문 skip 필터 제거 + `조문가지번호` 노출(`findtext`·never-raise — get_law_detail articles 조립 per-article try 부재라 절대 raise 금지·단위 테스트 잠금).
- **검색/doc-level/상세 3경로**(`main.py`): 종전 인라인 `f"JO{int(art_no):04d}"`(4자리 고정)를 공유 헬퍼 `_article_unit_id`로 전환 — 가지조문이 검색 결과·문서레벨 목록·상세에 6자리 JO로 유입, (번호,가지) 엄격 매칭.
- **프롬프트·README byte-sync**: `review_regulation` 프롬프트의 "가지조문(예: 제15조의2) 검색·상세조회 누락 가능" 한계 고지를 "v0.14.0부터 검색·상세조회 지원 — 누락 아님" 지원 안내로 정정(README 임베드 사본 동기화).
- **`rule_sets.yaml` known_limitations 정정**(적대검증 지적): 41개 규정의 stale "가지조문 누락 가능/표현 불가/v0.3 예정" 경고 제거 — 가지조문 지원으로 false·자기모순(standalone 12건 삭제·긴 LIVE 검증 문자열 끝 trailing 절 29건 trim). 그 결과 known_limitations가 빈 3건(innovation_act·innovation_rule·sector_kt_rule)은 dangling key 제거(Pydantic `default_factory=list`).
- **`_article_branch_no` 강건화**(적대검증 지적): 반환 `int → int|None`·`len ≤ 2` 가드(초장문 ASCII 가지번호의 CPython `int()` 변환 상한 raise 방지·never-raise)·비숫자/비ASCII/3자리+ 가지는 0(본조문 aliasing) 대신 None(skip) — 오도달·id 충돌 방지. `_article_unit_id`는 None 전파로 skip.
- **문서**: `docs/api_contract.md` §5.11 신설(가지조문 지원 상세)·§5.10 조문 목록 서술 v0.14.0 정합 정정·contract 0.10.0 버전 이력 행 추가.

## [0.13.1] - 2026-07-06

**manifest 현행 정합성 — 중소기업 기술혁신 촉진법 family 시행일·doc_id 동기화** — 2026-07-01 개정 발효로 현행이 바뀐 「중소기업 기술혁신 촉진법」(법률)·「동 시행령」 2건의 manifest fallback 식별자·시행일을 현행에 맞춘다. 런타임은 search-first(매 요청 규정명으로 최신 doc_id를 LIVE resolve)라 정상 조회 시 서비스 영향은 없으나, manifest 값은 (a) resolve 실패 시 **fallback doc_id** (b) `list_rule_sets`의 시행일 표시 (c) resolve 결과와 다를 때 응답의 "개정 반영: 시행일 X → Y" 안내에 쓰인다 — 구 값은 **이미 비현행인 구버전(법률 2026-05-26판·시행령 2026-02-01판)**을 fallback으로 서빙할 잠재 결함이자 `list_rule_sets` 표시 시행일의 stale 상태였다. **`/regs-audit` 전수 감사(law-api-prober 2026-07-06 LIVE): 52개 규정 중 CHANGED 2건은 이 둘뿐**(나머지 50건 현행 일치·resolve 실패 0). **Claude 직접 lawSearch 재검증(2026-07-06)**: 법률=단건 현행 행 MST 281987·시행 2026-07-01·공포 2025-12-30(제21289호)·일부개정 / 시행령=단건 현행 행 MST 287505·시행 2026-07-01·공포 2026-06-30(제36482호)·일부개정. 신 MST가 구 MST보다 작은 번호(281987<286263)인 것은 공포 시점 차이(공포 후 시행 대기분이 발효)일 뿐 오집 아님(C12 함정 준수 — 판정은 검색 행 기준·상세응답 시행일자 미사용). 조문·별표 수(법 33·별표 0 / 시행령 23·별표 4)는 신 MST에서도 LIVE 동일 → known_limitations 수치 불변, 검증일 주석만 갱신. `contract_version` **0.9.0 유지**(응답 schema·필드·shape·오류코드 불변 — 데이터 4필드만), 패키지 **minor** bump(현행 정합 = 버전 규칙상 마지막 숫자 +1: 0.13.0 → **0.13.1**). 지원 규정 수 **52개 불변**. **코드 로직 0줄**(서버 알고리즘·검색/랭킹/fallback/fan-out/transport/캐시·공유파서·외부 접속 URL 불변). 선례: v0.2.4(2026-06-12)가 동일 성격 「현행 시행일 정합」 패치를 무사고 배포. **`/disc` 3-AI(Claude+Codex+Gemini) R1 3/3 GO·blocking 0 수렴**(다른 backlog[structured 목 parity·평면 admrul 호 파싱·R5·B3·broad 드리프트] 동승 금지 — 단일 의도·최소 변경·outage 회피).

### Changed

- **manifest 현행화**(`rule_sets.yaml`, 순수 data 4필드): `sme_tech_act` `api_doc_id` 286263 → **281987**·`effective_date` 2026-05-26 → **2026-07-01** / `sme_tech_decree` `api_doc_id` 283001 → **287505**·`effective_date` 2026-02-01 → **2026-07-01**. 두 항목 `known_limitations`의 LIVE 검증일 주석 2026-06-12 → 2026-07-06(조문·별표 수치 불변).
- **문서 동기화**: README 지원 규정 표 2행 시행일(법률·시행령 2026-07-01) + Changelog 항목. `docs/api_contract.md` '(유지)' 행 추가.

### Added

- **정적 잠금 테스트 1건**(`tests/test_main.py`): `test_sme_tech_family_current_docids_v0131` — 두 규정의 `api_doc_id`·`effective_date`를 현행 값으로 결정론 고정(v0.9.0+ doc_id lock 패턴). ★acceptance의 `fetched_ok`는 search-first가 title로 resolve하므로 manifest fallback 값 오타를 못 잡아(도달만 확인), 정적 lock이 yaml 편집 오타를 pytest로 차단. + acceptance spec 무결성 가드 파라미터 1건(자동 발견). 테스트 313 → **315**.
- **acceptance spec**(`tests/acceptance/v0_13_1.py`): 갱신 대상 2건 도달(search '중소기업 기술혁신' fan-out) + 시행령 현행 MST(law:287505) 문서레벨 resolve 무오류 + 광역 '연구개발비' 무회귀. Level B에 현행 정합 grounding·무회귀 프롬프트.

## [0.13.0] - 2026-07-05

**R&D 규정 지원 확대 — 혁신도전형 고시 + 별지 정직 caveat (51 → 52)** — 과학기술정보통신부 소관 「혁신도전형 연구개발사업군의 지정 및 분류 기준 등에 관한 고시」를 추가한다. v0.11.0·v0.12.0에서 "별지 over-claim 위험"으로 별도 사이클로 defer됐던 차순위 후보를, **별지 정직 caveat**(핵심 분류 기준이 별지 1 수록이라 도구 조회 대상이 아님을 known_limitations로 직접 고지)와 함께 등록한다. v0.3.0~v0.12.0과 동일한 검증된 저위험 확대 패턴(**데이터(yaml)+프롬프트+테스트만**, 서버 알고리즘·응답 schema·검색/랭킹/fallback/fan-out/transport/캐시·공유파서·외부 접속 URL 불변)의 9번째 적용. 평면(flat) schema라 기존 평면 admrul 19건과 동형 — 신규 코드/파서 불요. **배포 전 LIVE 게이트(law-api-prober 2026-07-05): 정확 title + ministry=과학기술정보통신부 정확일치 resolve가 유일 현행 문서 1건**(동명·타부처 사본·트랙충돌 0·is_updated=False 현행·조문 8건 전부 tier-1[최대 1,272자]·발령번호 메타[고시 2025-4] 합성 가능). ★유일 쟁점이던 별지 실체는 유형 2종 서술(밀착관리형/공개경쟁형) 274자로 실측 확정 — 실무 가치가 높은 지정 절차(제5조)·지정 해제(제6조)·수의계약 등 특례(제7조)는 본문 조문 전문 제공. `contract_version` **0.9.0 유지**(응답 schema·필드·shape·오류코드 불변 — 데이터 corpus 확대만), 패키지 **major** bump(규정 확대 = 버전 규칙상 가운데 숫자 +1·마지막 0: 0.12.0 → **0.13.0**). 지원 규정 **51 → 52개**. **`/disc` 3-AI(Claude+Codex+Gemini) R1 3/3 GO·blocking 0 수렴**(caveat는 known_limitations 한정[전역 프롬프트 비대화 배제 3/3]·defer-all은 안정성 기여 없음·structured 목 parity·평면 admrul 호 파싱·R5·B3·broad 드리프트 전부 defer 유지. 운영 트랙[NAS Container Manager 부팅 작업·외부 감시 알림]은 서버 코드 무변경이라 본 패키지 밖 병행).

### Added

- **혁신도전형 고시 1건**(`rule_sets.yaml`, 순수 data): `innovation_challenge_criteria`(혁신도전형 연구개발사업군의 지정 및 분류 기준 등에 관한 고시, admrul 2100000253392, 고시 2025-4, 시행 2025-02-03, 평면 schema·조문 8·별표 0·별지 1[BP 미노출 by-design]·`unit_types: article`·`ministry: 과학기술정보통신부`). 지정 절차·지정 해제·수의계약 특례 등 실질 규정은 본문 조문 제공. ★known_limitations에 별지 정직 caveat 명시(핵심 분류 기준[밀착관리형·공개경쟁형]은 별지 1 수록 → 도구의 별표(BP) 조회 대상 아님·제4조는 위임 문구만·원문은 법제처 확인).
- **테스트 3건**: `test_innovation_challenge_registered_v0130`(tests/test_main.py — ministry·api_target·hierarchy_rank·unit_types·api_doc_id 결정론 고정 + ★별지 caveat 문구 잠금) / `test_review_prompt_mentions_innovation_challenge_v0130`(review 템플릿 적용 범위 노출) / `test_doc_level_forms_only_warning_innovation_challenge_v0130`(tests/test_tools.py — 별지 1건뿐인 doc-level에서 별표 목록 비움 + '본문 조회 불가' 경고[v0.2.2] 노출 잠금 = 별지 정직 caveat의 서버측 근거). + acceptance spec 무결성 가드 파라미터 1건(자동 발견). 테스트 309 → **313**.
- **acceptance spec**(`tests/acceptance/v0_13_0.py`): 신규 도달(search '혁신도전형' fan-out + doc-level resolve) + 광역 '연구개발비' 무회귀 + 제5조(최대 조문 1,272자) plain_text_verbatim + 제4조(별지 위임 문구) 전문 확인. Level B에 ★별지 정직성 프롬프트(호스트가 분류 기준 본문을 날조하지 않고 별지 수록·공식 원문 안내로 정직 처리하는지) 포함.

### Changed

- **카운트 동기화 51 → 52**: `_SERVER_INSTRUCTIONS`·review 템플릿 적용 범위(공통 행정규칙 행에 혁신도전형 고시 추가)·README(지원 규정 표[Tier 2 핵심 행정규칙 4→5개]·임베드 프롬프트 byte-sync·안내 문구)·내부 주석(캐시 headroom·fan-out 사이징·articles cap). `docs/api_contract.md` '(유지)' 행 추가.

## [0.12.0] - 2026-07-01

**R&D 규정 지원 확대 — 산업기술혁신사업 운영 지침 2건 (49 → 51)** — 산업통상부 소관 「산업기술혁신사업」 운영 지침 2건(보안관리요령·기술개발 평가관리지침)을 추가한다. 연구보안·성과평가는 본 서버의 명시 지원 범위이며, 이미 등록된 산업기술혁신촉진법 family(법·시행령·시행규칙·공통 운영요령)에 두 운영 트랙의 규정을 보강한다. v0.3.0~v0.11.0과 동일한 검증된 저위험 확대 패턴(**데이터(yaml)+프롬프트+테스트만**, 서버 알고리즘·응답 schema·검색/랭킹/fallback/fan-out/transport/캐시·공유파서·외부 접속 URL 불변). 둘 다 평면(flat) schema라 기존 「공통 운영요령」과 동형 — 신규 코드/파서 불요. **배포 전 LIVE 게이트(law-api-prober 2026-07-01): 2건 전부 정확 title + ministry=산업통상부 정확일치 resolve가 유일 현행 문서 1건**(동명 타부처 사본·트랙충돌 0·is_updated=False 현행 일치·핵심 콘텐츠 본문 조문 존재=별지/서식 trap 0). `contract_version` **0.9.0 유지**(응답 schema·필드·shape·오류코드 불변 — 데이터 corpus 확대만), 패키지 **major** bump(규정 확대 = 버전 규칙상 가운데 숫자 +1·마지막 0: 0.11.0 → **0.12.0**). 지원 규정 **49 → 51개**. **ultracode 워크플로 10에이전트 3렌즈(안정성·사용자가치·규율) 만장일치 #1 + `/goal-disc-out` R1 3/3(Codex+Gemini+Claude) GO·blocking 0 수렴**(scope는 산업부 운영 지침 2건으로 수렴 — 차순위 혁신도전형 고시는 핵심 분류기준표가 별지[BP 미노출]라 over-claim 위험이 있어 별도 사이클로 defer; B structured 목 parity·C 평면 admrul 호 파싱·D R5 길이상한·E B3 연결풀·F broad 드리프트 전부 defer).

### Added

- **산업기술혁신사업 운영 지침 2건**(`rule_sets.yaml`, 순수 data): `industry_tech_security`(산업기술혁신사업 보안관리요령, admrul 2100000122711, 고시 2018-88, 시행 2018-04-30, 평면 schema·조문 21·별표 1[BP0000 「보안관리 조치사항」 11,204자 본문 전문 tier-1]·서식 6[BP 미노출]·`unit_types: both`) / `industry_tech_evaluation`(산업기술혁신사업 기술개발 평가관리지침, admrul 2100000252016, 예규 139, 시행 2024-12-30, 평면 schema·조문 47·별표 3[BP0001 추진절차 46,830자·BP0002 16,511자 oversized→oversized_pointer / BP0003 1,651자 tier-1]·`unit_types: both`). 전건 `api_target: admrul`·평면 schema·`ministry: 산업통상부`. 보안등급 분류·보안대책(보안관리요령)·평가위원회·평가단·전문기관(평가관리지침) 등 실질 규정은 본문 조문 제공.
- **테스트 2건**(`tests/test_main.py`): `test_industry_tech_guidelines_registered_v0120`(ministry·api_target·hierarchy_rank·unit_types·api_doc_id 결정론 고정 — yaml drift 방어) / `test_review_prompt_mentions_industry_tech_guidelines_v0120`(review 템플릿 적용 범위에 신규 지침 2건 노출). + acceptance spec 무결성 가드 파라미터 1건(자동 발견). 테스트 306 → **309**.
- **acceptance spec**(`tests/acceptance/v0_12_0.py`): 신규 2건 도달(search '산업기술' fan-out + doc-level resolve 2건) + 광역 '연구개발비' 무회귀 + 보안관리요령 별표 BP0000(11,204자) plain_text_verbatim tier-1 + 평가관리지침 별표 BP0001(46,830자) oversized_pointer(정직 처리) 확인.

### Changed

- **카운트 동기화 49 → 51**: `_SERVER_INSTRUCTIONS`·review 템플릿 적용 범위(사업 운영규정·요령 행에 신규 2건 추가)·README(지원 규정 표[산업부 5→7개]·임베드 프롬프트 byte-sync·안내 문구)·내부 주석(캐시 headroom·fan-out 사이징·articles cap). `docs/api_contract.md` '(유지)' 행 추가.

## [0.11.0] - 2026-06-30

**R&D 규정 지원 확대 — 과기정통부 연구산업진흥법 family 3건 (46 → 49)** — 과학기술정보통신부 소관 「연구산업진흥법」 family(법·시행령·시행규칙)를 추가한다. 연구산업(연구개발서비스업·연구장비산업 등) 진흥 트랙은 현 corpus(혁신법·부처별 R&D·핵심 행정규칙)에 미수록된 갭으로, 연구개발서비스 위탁·연구장비 활용 등 연구행정 실무 참조도가 있다. v0.3.0~v0.10.0과 동일한 검증된 저위험 확대 패턴(**데이터(yaml)+프롬프트+테스트만**, 서버 알고리즘·응답 schema·검색/랭킹/fallback/fan-out/transport/캐시·공유파서·외부 접속 URL 불변, v0.10.1 공유파서 `_build_article_content` 불침투). **배포 전 LIVE 게이트(law-api-prober 2026-06-30): 3건 전부 정확 title + ministry=과기정통부 정확일치 resolve가 유일 현행 문서 1건**(동명충돌·부처 사본·트랙충돌·oversized 0·중복 0·is_updated=False 현행 일치). 전건 중첩 schema라 v0.10.1 호 아래 목 파싱 혜택 자동 적용. `contract_version` **0.9.0 유지**(응답 schema·필드·shape·오류코드 불변 — 데이터 corpus 확대만), 패키지 **major** bump(규정 확대 = 버전 규칙상 가운데 숫자 +1·마지막 0: 0.10.1 → **0.11.0**). 지원 규정 **46 → 49개**. **ultracode 워크플로 10에이전트 3렌즈(안정성 9.5·사용자가치·규율) 만장일치 #1 + `/goal-disc-out` R1 3/3(Codex+Gemini+Claude) GO·blocking 0 수렴**(scope는 family 3건으로 수렴 — 차순위 혁신도전형 고시는 핵심 분류기준표가 별지[BP 미노출]·평면 머신뷰 갭으로 over-claim 위험이 있어 별도 사이클로 defer; B structured 목 parity·C 평면 admrul 호 파싱·D R5 길이상한·E B3 연결풀·F broad 드리프트 전부 defer).

### Added

- **과기정통부 연구산업 R&D family 3건**(`rule_sets.yaml`, 순수 data): `research_industry_act`(연구산업진흥법, MST 231603, 법률, 시행 2021-10-21, 조문 18·별표 0·`unit_types: article`) / `research_industry_decree`(시행령, MST 261923, 대통령령, 시행 2024-06-01, 조문 23·별표 2[전부 별표구분='별표'·최대 ~5,167자 본문 전문 tier-1]·`unit_types: both`) / `research_industry_rule`(시행규칙, MST 262117, 과학기술정보통신부령, 시행 2024-06-01, 조문 4·별표 0·서식 15건[별표구분='서식'=BP 미노출]·`unit_types: article`). 전건 `api_target: law`·중첩 schema·`ministry: 과학기술정보통신부`. 연구산업 육성·전담기관·지원사업 골격 보유.
- **테스트 2건**(`tests/test_main.py`): `test_research_industry_family_registered_v0110`(ministry·api_target·hierarchy_rank·unit_types·api_doc_id[MST] 결정론 고정 — yaml drift 방어) / `test_review_prompt_mentions_research_industry_family_v0110`(review 템플릿 적용 범위·cross-check 라우팅 행). + acceptance spec 무결성 가드 파라미터 1건. 테스트 303 → **306**.
- **acceptance spec**(`tests/acceptance/v0_11_0.py`): 신규 3건 도달(search '연구산업' + 법률/시행규칙 doc-level) + 광역 '연구개발비' 무회귀 + 시행령 별표(≤5,167자) plain_text_verbatim tier-1 확인.

### Changed

- **카운트 동기화 46 → 49**: `_SERVER_INSTRUCTIONS`·review 템플릿 적용 범위(연구산업 R&D family 행 + cross-check 라우팅 추가)·README(지원 규정 표·임베드 프롬프트 byte-sync·안내 문구)·내부 주석(stale '43규정' → 49 정정). `docs/api_contract.md` '(유지)' 행 추가.

## [0.10.1] - 2026-06-30

**law 호(號) 아래 목(目) 본문 파싱 — 조문 content 완전성 보강 (content-only)** — v0.10.0 배포 후 브라우저 라이브 eval에서 실관측된 유일한 미흡(호스트가 「기업부설연구소 시행령 제6조①제1호 각 목 = 기업유형별 연구전담요원 수 기준」이 도구 content에 미수록임을 정직 고지·날조 0)을 해소한다. 원인 = `_build_article_content`가 조문내용→항(項)→호(號)까지만 순회하고 호 아래 목(目)을 미수록 — LIVE 실측상 호내용은 도입문("다음 각 목의 구분에 따른…")만 담고 실제 기준 수치(소기업 3명 등)는 `<목내용>`에만 존재하여, 도구의 핵심 가치인 grounded verbatim 인용에서 원문 자체가 누락됐다. **수혜 범위 = law 트랙 system-wide**(law-target 26문서 중 19문서·234개 목 보유, 혁신법 시행령·산업기술 시행령 등 핵심 포함; admrul은 전부 평면 schema라 목이 이미 inline 노출·무영향, 중첩 schema admrul 0건). **content-only 축소판** — 목 본문을 기존 content 문자열에 4-space indent로 포함시키는 완전성 수정이라 응답 schema·필드·provision_id·검색/랭킹/fallback/fan-out/transport·공유파서 인터페이스·외부 접속 URL 불변 → `contract_version` **0.9.0 유지**, 패키지 **minor** bump(정확도/완전성 소규모 = 버전 규칙상 마지막 숫자 +1: 0.10.0 → **0.10.1**). 지원 규정 **46개 불변**. **fault-isolation**: 목 순회는 `findtext`+`(x or "").strip()`+omit으로 never-raise(ElementTree semantics상 raise 불가) — `get_law_detail`의 articles 조립에 per-article try/except가 없어 목 코드가 예외를 던지면 문서 detail 전체가 실패하므로, 절대 raise하지 않는 형태로만 작성하고 단위 테스트로 불변식을 잠금. **적대검증 `/goal-disc-out` R1 3/3(Codex 축소GO·Gemini 측정후·Claude GO) — content-only 설계·구현 디테일 만장일치 수렴, GO/DEFER 분기는 '측정 battery로 배포 게이트'라는 동일 요구로 귀결(blocking 0)**. structured(article_structure) parity·평면 admrul 정규식 분해(v0.7.0 백로그)·규정 확대는 scope_out(별도 사이클).

### Changed

- **`_build_article_content`(live_api.py)**: 호(號) 순회 내부에 `for mok in ho.findall("목")` 추가 — 목 본문(`<목내용>`)을 4-space indent(호 2-space의 하위 계층)로 content에 append. 목번호 prefix("가.")는 항·호와 동일하게 보존(strip 안 함). content-only(structured 머신뷰·doc-level/size-tier 조립 무변경). 목을 가진 조문의 `content`·검색 매칭 대상에 목 텍스트가 새로 포함됨(additive 완전성 개선). 목 보유 조문 content 증가분은 기존 v0.6.0 size-tier 가드가 처리(예산 15,700 초과 시 oversized_pointer graceful 강등).

### Added

- **테스트 2건**(`tests/test_tools.py`): `test_build_article_content_includes_mok_v0101`(목 보유 조문 content에 목 텍스트·4-space indent·목번호 prefix 보존 검증) / `test_build_article_content_malformed_mok_never_raises_v0101`(결손·빈 목 element가 raise 없이 omit — fault-isolation 불변식 잠금). 테스트 300 → **302**.
- **acceptance spec**(`tests/acceptance/v0_10_1.py`): 목 보유 조문(corp_lab_decree JO0006) size 무회귀(plain_text_verbatim 유지) + 광역 '연구개발비'·'기업부설연구소' 검색 무회귀. 목 텍스트 실수록·검색 도달은 배포 전 측정 battery(직접 LIVE 프로브)가 검증.

## [0.10.0] - 2026-06-29

**R&D 규정 지원 확대 — 과기정통부 기업부설연구소 family 3건 (43 → 46)** — 스태빌리티 트랙(B2)이 측정상 충분함을 확인한 뒤(좀비-슬롯 fault-injection: 좀비창 ~5s·graceful degradation 이미 작동 → v0.9.2 보류·B3 0-target defer), 데이터/정확도 트랙으로 복귀하여 과학기술정보통신부 소관 「기업부설연구소등의 연구개발 지원에 관한 법률」 family(법·시행령·시행규칙)를 추가한다. 기업부설연구소·연구개발전담부서 인정요건은 기업참여 R&D 과제의 참여자격·간접비 산정 근거로 사용자(연구자·대학행정·전문기관·PM) 직접도가 높다. v0.3.0~v0.9.0과 동일한 검증된 저위험 확대 패턴(**데이터(yaml)+프롬프트+테스트만**, 서버 알고리즘·응답 schema·검색/랭킹/fallback/fan-out/transport/캐시·공유파서·외부 접속 URL 불변). **배포 전 LIVE 게이트(law-api-prober 2026-06-29): 3건 전부 정확 title + ministry=과기정통부 정확일치 resolve가 유일 현행 문서 1건**(동명충돌·부처 사본·폐지본 혼재 0·C12 미래분리시행 0). `contract_version` **0.9.0 유지**(응답 schema·필드·shape·오류코드 불변 — 데이터 corpus 확대만), 패키지 **major** bump(규정 확대 = 버전 규칙상 가운데 숫자 +1·마지막 0: 0.9.1 → **0.10.0**). 지원 규정 **43 → 46개**. **ultracode 워크플로 10에이전트 3렌즈(안정성·가치·규율) 만장일치 #1 + `/goal-disc-out` R1 3/3(Codex+Gemini+Claude) GO·blocking 0 수렴**(나머지 후보[평면 admrul 호 파싱·R5 길이상한·broad 드리프트·검색 recall·B3 연결풀] 전부 defer).

### Added

- **과기정통부 기업부설연구소 R&D family 3건**(`rule_sets.yaml`, 순수 data): `corp_lab_act`(기업부설연구소등의 연구개발 지원에 관한 법률, MST 282553, 법률, 시행 2026-02-01, 조문 27·별표 0·`unit_types: article`) / `corp_lab_decree`(시행령, MST 282915, 대통령령, 시행 2026-02-01, 조문 20·별표 3[전부 별표구분='별표'·최대 ~6,194자 본문 전문 tier-1]·`unit_types: both`) / `corp_lab_rule`(시행규칙, MST 283223, 과학기술정보통신부령, 시행 2026-02-01, 조문 14·별표 1[별표0000·20,358자 oversized → 기존 v0.6.0 size-tier 가드가 `oversized_pointer`로 처리·코드 무변경]+서식 15건[별표구분='서식'=BP 미노출]·`unit_types: both`). 전건 `api_target: law`·중첩 schema·`ministry: 과학기술정보통신부`. 기업부설연구소·연구개발전담부서 인정요건·지원 골격 보유.

### Changed

- `review_regulation` 프롬프트(`_REVIEW_PROMPT_TEMPLATE`) 적용 범위 목록에 "Tier 1 (Sector — 기업부설연구소 R&D family)" 행 + 3단계 cross-check 라우팅(기업부설연구소/연구개발전담부서/연구소 인정 → `corp_lab_*`) 추가. README 임베드 사본 byte-sync(`test_readme_embedded_prompt_matches_template`). 적용 범위 카운트 43 → 46개(서버 instructions·프롬프트·README·도구 description 동기화).

### 검증

- 테스트 신규(기업부설연구소 family 등록 단언 `test_corp_lab_family_registered_v0100` + review 프롬프트 family 행 `test_review_prompt_mentions_corp_lab_family_v0100` + `list_rule_sets` 46건 id 완전일치 갱신). acceptance `v0_10_0.py`(신규 3건 `fetched_ok`·기업부설 `returned`·시행규칙 별표0000 `oversized_pointer` `field_equals`·법률 문서레벨 도달). **배포 전 게이트**: LIVE 게이트(law-api-prober)·라이브 size 스모크(시행규칙 BP0000 → oversized_pointer)·NAS 신이미지 cold fan-out 스모크 N=46(`skipped`/`timeout`/`rate_limited`=0·wall 예산 내)·롤백태그 `:0.9.1-rollback` 보존 → PyPI → GitHub → 플러그인 → NAS 마지막.

## [0.9.1] - 2026-06-25

**fan-out 전용 bounded executor — 풀 큐잉 latency 제거 (B2 스태빌리티)** — v0.9.0 배포 후 측정(2026-06-25, 코드 무변경)에서 `search_provision`의 cold fan-out(N=43)이 **NAS 기본 8스레드 ThreadPoolExecutor 큐잉**에 지배됨을 확정(executor 스레드 sweep 8→64 = cold wall 8.35s→4.88s·slow_rule 42→5·NAS 실 cold 7.4~7.7s·slow 41~43). law.go.kr offload(resolve+detail)를 NAS 코어 수에 종속된 default pool에서 **전용 bounded executor(`max_workers=32`)로 격리**해 큐잉 latency를 제거한다(로컬 신코드 cold 8스레드 8.35s 대비 32-worker ~5.0s). 응답 schema·검색/랭킹/fallback·외부 접속 URL·규정 수 불변, `contract_version` **0.9.0 유지**, 패키지 **minor** bump(안정성·정확도 = 마지막 숫자 +1: 0.9.0 → **0.9.1**). 변경은 전부 **요청-격리 도구 로직 + client 내부**(부팅/HTTP transport/health/캐시-bootstrap 비의존 — executor는 import 시 생성하나 `ThreadPoolExecutor`는 submit 전 스레드 미spawn이라 boot 무의존). **적대검증 `/goal-disc-out` 2R(Codex+Gemini+Claude) 수렴·blocking 0**: 전용 executor(부팅/transport 영향 없는 격리) > `set_default_executor`(fastmcp 소유 루프 변경 위험), 마이그레이션 5곳 전부(공유 `_resolve_doc_id` 일관성), TTLCache thread-safety 동반(아래).

### Changed

- **fan-out 전용 executor**(`main.py`): 모듈 레벨 `_FANOUT_EXECUTOR = ThreadPoolExecutor(max_workers=32, thread_name_prefix="rnd-fanout")` + offload 단일 진입점 `_run_offloaded(fn, *args)`(= `loop.run_in_executor(_FANOUT_EXECUTOR, contextvars.copy_context().run, fn, *args)` — `asyncio.to_thread` 등가이되 default pool 대신 전용 풀·submit마다 새 `copy_context`). law.go.kr offload 5곳(`_resolve_doc_id`·search_provision detail 2·get_provision_detail detail 2)을 전부 이전. 전 사용자(`_client_by_key`) 합산 동시 law.go.kr 연결을 32로 bound(backpressure). 사이징 32: N=43 cold peak 동시성 ≈43 → 일부 잠깐 큐잉·48은 정부 API 동시연결 rate-limit/예의 위험(게이트서 `rate_limited` 관측 시 24로 하향).
- **TTLCache thread-safety**(`live_api.py`): 동시성을 8→32로 키우면 같은 client의 `TTLCache` 5종(thread-safe 아님 — `in`/`get`/`[]` read도 expire+링크 변경=mutation)에 동시 write가 늘어 내부 링크 corruption 위험. client당 `threading.Lock()`(`_cache_lock`)으로 **모든 cache touch만** 직렬화(`_check_caches`·`_record_failure`·직접 set 4곳·`resolve_latest_doc_id` id-resolution 직접 get/set 4곳). ★network(`_request_with_retry`)·XML 파싱은 절대 lock 밖(정적 가드 `test_cache_lock_never_wraps_network_or_parse`로 박제). 현 설계는 nesting 없음 → plain Lock(실수로 network를 감싸면 deadlock으로 fail-loud).

### 검증

- 테스트 **289 → 296**(B2 가드 7건: executor 구성·offload 코루틴·정적 `asyncio.to_thread` 0건·`_cache_lock` 존재·★lock-never-wraps-network 정적 게이트·contract 0.9.0·version 0.9.1). 로컬 cold fan-out 실측 32-worker **5.0s**(`rnd-fanout` 스레드 32 spawn 확인·default pool 미사용)·`--http` 부팅 스모크(serverInfo 0.9.1·instructions 43·import-time executor boot 무해). **배포 전 게이트**: NAS 신이미지 cold(wall 감소·`skipped`/`errors`/`rate_limited`=0)·LIVE acceptance(returned 무회귀)·실 diff 적대검증·롤백태그 `:0.9.0-rollback` 보존 → PyPI → GitHub → 플러그인 → NAS 마지막.

## [0.9.0] - 2026-06-24

**R&D 규정 지원 확대 2차 — 교육부 산학협력 family 3건 + 연구윤리 지침 (39 → 43)** — v0.8.0(교육부 학술진흥법) 배포·eval에서 단일 조문 타깃 질의가 MCP grounded로 작동함을 입증한 데 이어, 교육부 R&D의 또 다른 핵심 트랙인 대학 산학협력(산업교육진흥 및 산학연협력촉진법 family)과 연구진실성(연구윤리 확보를 위한 지침)을 추가한다. v0.3.0·v0.4.0·v0.8.0과 동일한 검증된 저위험 확대 패턴(**데이터(yaml)+프롬프트+테스트만**, 서버 알고리즘·응답 schema·검색/랭킹/fallback/transport/캐시·외부 접속 URL 불변). **배포 전 LIVE 검증 게이트(2026-06-24, `law-api-prober`): 4건 전부 정확 title + ministry=교육부 정확일치 resolve가 유일 현행 문서 1건**(트랙 충돌·동명이종·부처 사본 0·잘못된 부처 ministry 필터 격리 실증) → 순수 data·코드 가드 불요. 산학협력 3건은 law target·중첩 schema, 연구윤리 지침은 admrul 평면 schema(기존 fallback 자동). oversized 없음(시행령 별표1 ~1,856자 tier-1·시행규칙 부속문서는 전부 별지서식이라 BP 미노출). `contract_version` **0.9.0 유지**(응답 schema·필드·shape·오류코드 불변 — 데이터 corpus 확대만), 패키지 **major** bump(규정 확대 = 새 버전 규칙상 가운데 숫자 +1·마지막 0: 0.8.0 → **0.9.0**). 지원 규정 **39 → 43개**. (3-AI /disc 3/3 수렴: 후보 #1[규정 확대] 선정·#2[law-target broad 질의 외부 드리프트 완화 — N=1·실트래픽 후 재상정]·#5[B2/B3 스태빌리티 — transport 인접 outage 위험·트리거 미점화] 보류. scope=Andy 결정 '4건 한 번에' — fan-out 43은 cold 6.9s@39 → ~8s 추정으로 20s 예산 가드에 여유·배포 1회 = outage-risk 순간 최소화.)

### Added

- **교육부 산학협력 R&D family 3건**(`rule_sets.yaml`, 순수 data): `sanhak_act`(산업교육진흥 및 산학연협력촉진에 관한 법률, MST 267351, 법률, 시행 2025-06-21, 조문 46·별표 0) / `sanhak_decree`(시행령, MST 284767, 대통령령, 시행 2026-03-24, 조문 53·별표 1[BP0000·~1,856자 본문 전문 tier-1]) / `sanhak_rule`(시행규칙, MST 285257, 교육부령, 시행 2026-03-27, 조문 5·별표 0[부속문서 11건은 전부 별지서식=BP 미노출 → `unit_types: article`]). 전건 `api_target: law`·중첩 schema·`ministry: 교육부`. 대학 산학협력단·기술지주회사·협력연구소·산학연협력계약 등 R&D 골격 보유.
- **연구윤리 확보를 위한 지침 1건**(`rule_sets.yaml`, 순수 data): `research_ethics_guideline`(교육부 훈령 449호, ID 2100000226306, 시행 2023-07-17, 조문 35·별표 0, 평면 schema·fallback 자동·`ministry: 교육부`). 연구부정행위 범위·검증·조사위원회·연구진실성 — 전 부처 R&D 공통 고빈도 검토 주제. (LIVE 검증: 2026-06-24 게이트로 현행성·트랙 단건 resolve·schema·R&D 관련성 전건 확정.)

### Changed

- `review_regulation` 프롬프트(`_REVIEW_PROMPT_TEMPLATE`) 적용 범위 목록에 "Tier 1 (Sector — 산학협력 R&D family)" 행 + Tier 2 공통 행정규칙에 "연구윤리 확보를 위한 지침(교육부)" + 3단계 cross-check 라우팅(산학협력→`sanhak_*` / 연구윤리·연구부정행위·연구진실성→`research_ethics_guideline`) 추가. README 임베드 사본 byte-sync. 적용 범위 카운트 39 → 43개(서버 instructions·프롬프트·README·도구 description 동기화).
- 검색 캐시 maxsize(64)는 N=43<64라 영향 없음(불변).

## [0.8.0] - 2026-06-24

**R&D 규정 지원 확대 — 교육부 학술진흥법 family 3건 (36 → 39)** — v0.7.0 배포 후 라이브 eval에서 도구 호출 게이팅·발견성은 개선됐으나, 핵심 미션("국가법령정보 OpenAPI 수록 R&D 규정을 최대한 지원")의 다음 자연스러운 진전은 교육(학술) 분야 누락 해소다. 학술연구지원사업은 대학·연구자의 핵심 R&D 트랙임에도 그 모법인 학술진흥법 family가 미수록이라, 관련 질의가 "범위 밖→일반 학습지식(stale 위험)"으로 처리됐다. 검증된 저위험 확대 패턴(v0.3.0 보건복지부·v0.4.0 질병관리청과 동일하게 **데이터(yaml)+프롬프트+테스트만**, 서버 알고리즘·응답 schema·검색/랭킹/fallback/transport/캐시·외부 접속 URL 불변)으로 교육부 학술진흥법 3건(법·시행령·시행규칙)을 manifest에 등록한다. **배포 전 LIVE 검증 게이트(2026-06-23) 확정: 정확 title + ministry=교육부 정확일치 resolve가 유일 현행 문서 1건을 집음**(트랙 충돌·동명이종·약칭 0 — 과거 '트랙 판별 가드' 우려는 이 3건 family에는 LIVE 근거 없음 → 순수 data로 안전, 코드 가드 불요). 3건 전부 law target·중첩 schema(평면 admrul 호 구조 backlog와 무관)·oversized 없음(최대 별표 13,213자 < size-tier 예산 15,700 → 본문 전문 tier-1). `contract_version` **0.9.0 유지**(응답 schema·필드·shape·오류코드 불변 — 데이터 corpus 확대만), 패키지 **major** bump(규정 확대 = 새 버전 규칙상 가운데 숫자 +1·마지막 0: 0.7.x → **0.8.0**). 지원 규정 **36 → 39개**. (3-AI /disc 3/3 수렴: 후보 C[규정 확대] 선정·A[평면 admrul 호 구조 파싱 — N=1 host 산술·content 정확·정규식 false-split이 빈 배열보다 위험]·B[R5 비-본문 필드 길이 가드 — 현행 막을 대상 0건의 3번째 연속 예방]은 보류. LIVE 게이트가 Codex[검증된 family]·Gemini[순수 data] 분기를 동시 충족.)

### Added

- **교육부 학술진흥법 family 3건**(`rule_sets.yaml`, 순수 data): `hakjin_act`(학술진흥법, MST 230413, 법률, 시행 2021-06-23, 조문 23·별표 0) / `hakjin_decree`(학술진흥법 시행령, MST 245227, 대통령령, 시행 2022-11-08, 조문 23·별표 3·최대 2,937자) / `hakjin_rule`(학술진흥법 시행규칙, MST 220701, 교육부령, 시행 2020-10-13, 조문 7·별표 1·13,213자=본문 전문 tier-1). 전건 `api_target: law`·중첩 schema·`ministry: 교육부`. 시행령은 학술연구지원사업의 선정(제6조)·협약(제7조)·출연금/사업비·결과보고·평가·전담기관·연구부정·제재 등 R&D 연구행정 절차 골격을 직접 보유. (LIVE 검증: 2026-06-23 게이트 — `law-api-prober`로 현행성·트랙 단건 resolve·schema·R&D 관련성 전건 확정.)

### Changed

- `review_regulation` 프롬프트(`_REVIEW_PROMPT_TEMPLATE`) 적용 범위 목록에 "Tier 1 (Sector — 학술진흥 R&D family): 학술진흥법·시행령·시행규칙(교육부)" 행 추가(host가 교육부 학술 규정을 범위 밖 오분류하지 않도록). README 임베드 사본 byte-sync. 적용 범위 카운트 36 → 39개(서버 instructions·프롬프트·README 동기화). `plugin.json`/`marketplace.json` description에 교육부 추가.
- 검색 캐시 maxsize(64)는 N=39<64라 영향 없음(불변).

## [0.7.0] - 2026-06-22

**조문(JO) 발견성 갭 해소 — 문서 레벨 조문 목록** — v0.6.0 배포 후 라이브 eval에서, 호스트가 행정규칙(admrul) 평면 schema의 특정 조문(예: 제2조)을 찾을 때 (a) 문서 레벨 `get_provision_detail` 응답이 `annexes`(별표) 목록은 주면서 `articles`(조문) 목록은 주지 않고 `articles_count`(숫자)만 노출해 JO provision_id를 알 수 없고, (b) 조문 번호("제2조")로는 키워드 검색도 안 맞아, 결국 외부 law.go.kr로 우회하는 갭이 실관측됐다(도구가 정답을 줄 수 있는데도 호스트가 식별자 발견에 비용 지출). 이미 검증된 v0.2.1 `annexes` 목록 패턴을 조문(JO)으로 그대로 재현해, 문서 레벨 응답에 `articles` 목록을 additive로 추가한다. fan-out 부하 0·doc-level 응답 직렬화 1점·검증된 패턴 재사용 = "안정적 제공 + 최소 변경" 정합. **배포 전 36규정 전수 LIVE 실측: 조문 수 최대 규정(rnd_funding_standard 117조문)도 목록 직렬화 ~12.9k자(16k 예산의 80.6%)로 예산 내** — size 백스톱은 데이터 증가·schema 변화 대비 방어망이며 현행 데이터에서는 미발동. `contract_version` **0.8.0 → 0.9.0**(응답 schema additive), 패키지 **minor** bump. 검색/랭킹/fallback/fan-out/transport/bootstrap/캐시 메커니즘·외부 접속 URL·규정 수(36) 불변. (3-AI /disc 3/3 수렴: 후보 #2 선정·#1[R5 비-본문 필드 길이 가드 — 현행 막을 대상 0건의 예방]은 거대 필드 노출 변경과 짝지을 때로 보류.)

### Added

- **document-level `articles` 목록**(additive): `get_provision_detail`(unit_id 생략) 응답에 조문 목록 `articles: [{provision_id, label, title}]` 추가(본문 미포함) — 별표 `annexes` 목록의 조문(JO) 대응. 호스트가 특정 조문의 JO provision_id를 추측/외부 우회 없이 제목으로 선택. **ASCII 숫자 조문번호만**: `live_api` 파서가 가지조문(제N조의M)·장절 wrapper를 이미 제외하므로 본 조문만 노출하고, 상위첨자 '²'(`isdigit` True·`int()` ValueError)·4,300자리 초과 장문 숫자(CPython int 변환 상한)는 `isascii`+`isdigit`+`try/except` 가드로 skip. document-level 목록과 `get_provision_detail`(JO) 분기가 **동일 int 가드**를 써서, 앞선 비정상 조문번호 1건이 목표 조문 도달을 깨뜨리지 않음(노출 provision_id가 전부 JO 조회 가능·죽은 id 0). dedup은 방어적(가지조문 제외로 정상 데이터엔 중복 없음·첫 등장=JO first-match 정합). `articles_count`(파싱된 실제 조문 수 — 가지·wrapper 제외)와 목록 길이는 정상 데이터에서 동일(다른 경우는 백스톱 절단 또는 비정상 번호 skip뿐).
- **size 백스톱**(신규 `articles_truncated` 플래그): `articles` 목록 추가 후 **최종 응답을 실제 `json.dumps`로 측정**해 16,000자 초과 시 `articles_truncated=true` + 경고를 표시하고 목록 뒤에서 항목을 제거(추정 산식이 아니라 완성 응답 자체 측정 — 직렬화 separator·메타데이터 누적 오차에 안전). 보장: **`articles` 목록 항목(volume)이 응답을 예산 너머로 키우지 않음**(목록은 절단으로 bound). ★base(annexes 목록·revision_notice 등 무한 비-본문 필드)만으로 이미 예산 한계 근처/초과면 pre-existing R5 system-wide 사안(단일 의도 밖)이라 목록을 비우고 본 feature가 추가한 플래그·경고를 되돌려 base를 더 키우지 않음(graceful degrade). 이 R5 극단에서 빈 additive `articles` 키(~16자)가 base를 미세 초과시킬 수 있으나 모든 additive 필드(v0.5.0 version 메타 ~106자 등)가 공유하는 base-bloat이며 v0.7.0의 16자는 기존 R5 주원인을 실질적으로 확대하지 않음(106자보다 작음). 16,000은 25,000 TOKEN의 보수 proxy(char≠token)라 실한도 여유. build는 `_DOC_ARTICLES_MAX`(600)로 bound(비정상 대량 입력 O(n²)·메모리 방어). 현행 36규정 실측상 미발동(최악 117조문 ~12.9k자).

### Changed

- `get_provision_detail` docstring·`review_regulation` 프롬프트(`_REVIEW_PROMPT_TEMPLATE`) 5단계에 "특정 조문 provision_id가 불확실하면 추측 말고 문서 레벨 `articles` 목록에서 선택" 안내 1문장 미러링(기존 `annexes` 안내와 동형). README 임베드 사본 byte-sync. `_SERVER_INSTRUCTIONS`(서버 전역)는 불변(표면 최소화).
- `contract_version` 0.8.0 → **0.9.0** (`provision_id.py`, `docs/api_contract.md` §5.10 신설·§6 이력).

## [0.6.0] - 2026-06-21

**get_provision_detail 조문(JO) 응답 크기 계층화 — 무한 입력 경계 폐쇄** — v0.5.0 적대검증(R5)이 식별한 "OpenAPI 공급 필드가 비정상적으로 길면 응답 총량이 16k char 예산을 넘겨 호스트에서 truncation/거부될 수 있다"는 경계 중, 유일하게 무가드로 남아 있던 `get_provision_detail` **조문(JO)** 경로(content + 중복 article_structure)에 기존 검증된 별표 size-tier 패턴을 확장한다. fan-out 부하 0·응답 직렬화 1점·검증된 패턴 재사용 = "안정적 제공 + 최소 변경"에 최적 정합. **배포 전 36개 규정 1,125개 조문 전수 LIVE 실측 결과 어떤 조문도 임계(15,700자)를 넘지 않아(최대 직렬화 12,180자) 현행 36규정은 전건 기존 거동(tier-1) 그대로** — 본 변경은 현재 overflow 버그픽스가 아니라 미래 대형 조문·schema 변화 대비 예방이다. `contract_version` **0.7.0 → 0.8.0**(degraded tier 신규 필드 + 거동), 패키지 **minor** bump. 검색/랭킹/fallback/fan-out/transport/bootstrap/캐시 메커니즘·외부 접속 URL·규정 수(36) 불변.

### Added

- **조문(JO) detail size-tier 공통 helper `_build_article_detail`**(별표 `_build_annex_detail` 패턴 확장). 3-tier: ① `content + article_structure ≤ 예산` → 전문 verbatim + structure(**종전과 동일 — 공통 경로 무변경·degraded 전용 필드 미출현**) / ② `content ≤ 예산 < content+structure` → 중복 머신뷰 `article_structure`를 `null`로 생략(신규 `structure_omitted=true` + 구조 미참조 `format_instructions` 변형 + 경고 1줄), **content는 전문(plain_text_verbatim) 유지**(중대형 조문도 본문 인용 가능) / ③ `content > 예산` → 본문 미수록 `content_format=oversized_pointer`(+`content_available=false`·`verbatim_quote_allowed=false`·`is_complete=false`·`omitted_reason`·`omitted_char_count`·`required_action`·`document_source_url` 1순위 + search_provision 안내). 예산 = `_ANNEX_DETAIL_CHAR_BUDGET`(16,000) − `_ANNEX_DETAIL_HEADROOM`(300).
- 전문/구조생략 tier에 **사후주입(version 메타·revision_notice) 후 size 백스톱** — 최종 직렬화가 16,000을 넘으면 `_build_article_detail(force_oversized=True)`로 oversized 강등(별표 BP 백스톱과 동일). 본문(content)이 size 주범인 경우를 해소하며, 본문 외 무한 공급 필드(revision_notice·title 등)가 단독 초과하는 경우는 pre-existing system-wide 사안(R5 backlog·단일 의도 밖). 정상 데이터에서는 헤드룸이 사후주입을 흡수해 미발동.

### Changed

- `get_provision_detail` 조문(JO) 분기를 인라인 dict 조립에서 `_build_article_detail` 호출 + 백스톱으로 교체. 응답 길이 정책(§5 L144) "조문은 길이 제한 없음" → size-tiered로 갱신.
- `get_provision_detail` docstring에 JO size-tier 안내(대용량 조문은 article_structure 생략 또는 oversized_pointer). 신규 상수 `_VERBATIM_INSTRUCTIONS_NO_STRUCTURE`(구조 생략 tier용 정확성 안내).
- `contract_version` 0.7.0 → **0.8.0** (`provision_id.py`, `docs/api_contract.md` §5·§5.9 신설·§6 이력).

## [0.5.0] - 2026-06-21

**행정규칙 version 메타데이터 내재화 — 발령번호·종류 노출** — v0.4.1 라이브 eval에서 호스트가 「고시·예규 발령번호」를 MCP에서 얻지 못해 외부 웹으로 나가 구버전(stale) 번호·시행일을 단정하고, 심지어 등록된 규정을 "존재하지 않음"으로 false-negative 단정한 결함(프롬프트 3 SEVERE FAIL·프롬프트 4 FAIL)이 확정됐다. 도구가 발령번호를 직접 제공하면 외부-first 트리거 자체가 제거된다(데이터/schema 변경·호스트 무관 결정론). 행정규칙(admrul) 상세에서 발령번호·종류를 파싱해 `get_provision_detail` 응답에 additive 노출 + 동일 eval 사고의 false-negative 텍스트 가드 1문장. **admrul 한정**(law은 공포번호로 의미가 다르고 C12 합본 분리시행 함정 동반 — 별도·후순위). `contract_version` **0.6.0 → 0.7.0**(응답 schema additive), 패키지 **minor** bump. 검색/랭킹/fallback/fan-out/transport/bootstrap/캐시 메커니즘·외부 접속 URL·규정 수(36) 불변.

### Added

- **`get_provision_detail` 응답에 admrul version 식별자 3필드**(additive, doc-level·조문·별표 4-tier 전 성공 반환점 공통 helper `_admrul_version_meta`): `issuance_number`(raw 발령번호 "179"/"2026-25")·`regulation_kind`("예규"/"고시"/"훈령")·`version_label`(엄격 합성 "예규 제179호" — 종류가 허용값이고 번호가 검증 패턴일 때만, 부처명 prepend 금지·omit 규칙). 기존 `effective_date`(검색행 resolve)는 별도 필드 유지. `pid.doc_type=="admrul"`만 — law·오류 응답 미주입. LIVE 19건 전건 검증: 검색행 시행일 = 상세 시행일(C12-like split 0건)·발령번호·종류 누락 0건.
- `live_api.get_admin_rule_detail`이 상세 XML `<행정규칙기본정보>`의 `발령번호`·`행정규칙종류`를 파싱(nested/flat schema 공통). fault-isolated(`findtext`+`strip`+누락 시 "") — 본 파서는 검색 fan-out도 공유하므로 예외를 던지지 않는다.

### Changed

- 서버 `_SERVER_INSTRUCTIONS`(initialize 메타데이터)에 (a) 행정규칙 현행 발령번호·종류는 응답의 `issuance_number`·`regulation_kind`·`version_label`로 확인, (b) **MCP에 등록·검색된 규정을 외부 검색에서 찾지 못했다는 이유만으로 존재하지 않는다고 단정하지 말 것**(false-negative 가드 — 프롬프트 3 직접 겨냥) 2개 취지 append. 기존 가드 구절 전부 보존(append-only).
- `get_provision_detail` docstring에 admrul 응답의 version 필드 안내 1문장(기존 구절 보존).
- `contract_version` 0.6.0 → **0.7.0** (응답 additive 필드 — `provision_id.py`, `docs/api_contract.md` §5.8 신설·§6 이력).

## [0.4.1] - 2026-06-21

**외부 웹 본문 폴백 차단 — 규정 본문은 도구(get_provision_detail)로만** — v0.4.0 라이브 eval 프롬프트 4(비교 질의)에서 호스트가 등록된 규정을 '존재 확인용'으로만 쓰고 규정 본문은 외부 law.go.kr에서 가져와 구버전(stale) 고시번호·시행일을 인용한 결함(컴플라이언스 위험)이 확정됐다. 원인은 데이터 부재가 아니라 호스트 행동 — 현 프롬프트가 'get_provision_detail content를 verbatim 사용'은 지시하나 '외부 웹 본문 폴백 금지'는 명시하지 않은 빈칸이었다. 프롬프트/docstring 텍스트만(코드 로직·검색/랭킹/fallback·응답 schema·transport·외부 접속 URL·규정 수 불변), `contract_version` **0.6.0 유지**, 패키지 **PATCH** bump. ★Level-B(호스트 의존) 완화이며 결정적 fix가 아니다 — 효능은 배포 후 수동 eval로 확인한다.

### Changed

- `review_regulation` 템플릿(`_REVIEW_PROMPT_TEMPLATE`) 4단계(상세 조회)에 지시 3개 추가(README 임베드 사본 byte-sync): (1) 규정 조문·별표 본문은 임의 웹검색·law.go.kr 직접 열람 등 외부 웹에서 대체·보충하지 말고 `get_provision_detail` content로 확인 — 단 `content_format`이 `plain_text_verbatim`이 아닌 경우 응답이 제공한 공식 원문 링크 확인 예외 보존, (2) 고시·예규 번호 등 MCP 응답(content·effective_date 등 제공 필드)에 없는 현행 식별자는 외부 웹에서 단정하지 말고 "MCP 응답에서 확인되지 않음" 표시, (3) 둘 이상 규정·조문 비교 시 근거 `provision_id`를 전부 조회하고 같은 id는 결과 재사용(중복 호출 금지).
- `get_provision_detail` docstring 첫 문단에 content가 본문 권위 출처·외부 웹 본문 폴백 금지·non-verbatim 공식 원문 예외·미제공 식별자 외부 단정 금지 1문장 append(기존 '사용 시점'·'추측하지 마십시오' 보존).
- 서버 `_SERVER_INSTRUCTIONS`(initialize 메타데이터)에 지원 범위 내 규정 본문의 외부 웹 폴백 금지 1문장 append — `review_regulation`을 호출하지 않는 비교/자유서술 질의(프롬프트 4 유형) 경로 커버. 기존 도구 호출 유도·fail-closed·범위 외 정직성 가드 구절 전부 보존(append-only).

## [0.4.0] - 2026-06-20

**질병관리청 R&D 규정 지원 확대 (32 → 36)** — v0.3.0 라이브 eval에서 질병관리청 연구개발 관리 규정이 미지원이라 일반 학습지식(구버전 고시 2100000222940/2023-05-03)을 현행처럼 단정한 stale 패턴이 재실증됐다. 미지원 규정의 현행성 갭은 프롬프트 가드로 완화는 되나 근본 해소는 도구 등록뿐 — 질병관리청 R&D family 4건을 manifest에 등록한다. 단일 의도(질병관리청 지원 확대), 데이터+캐시 상수+텍스트+테스트만(서버 request 메커니즘·응답 schema·검색/랭킹/fallback·transport·외부 접속 URL 불변), `contract_version` **0.6.0 유지**. 지원 규정 **32 → 36개**.

### Added

- **질병관리청 R&D family 4건**(전건 admrul·평면 schema·별표 0·ministry=질병관리청, LIVE 검증 2026-06-20): 질병관리청 연구개발 관리 규정(2100000279440·시행 2026-05-18)·질병관리청 연구개발사업 전문기관 지정 고시(2100000277984·2026-04-15)·질병관리청 국가연구개발 시설·장비 관리 규정(2100000214227·2022-08-31)·(질병관리청)국가연구개발성과 범부처 이어달리기 프로젝트 공통운영 지침(2100000197858·2021-02-02). 이어달리기 지침은 OpenAPI에 19개 부처별 사본이 '(부처명)…' 접두 제목으로 존재하므로, manifest title을 부처 접두 포함 정식명으로 등록하여 resolve가 질병관리청 사본을 정확히 집도록 했다(접두 없는 제목은 정확일치 0 → manifest fallback으로 현행성 추적 불가).
- `review_regulation` 템플릿·README 지원 규정 목록·cross-check 라우팅에 질병관리청 R&D family 추가, 도구 prompt·플러그인·마켓플레이스 description에 질병관리 도메인 반영. 서버 instructions·README 지원 카운트 32→36 동기화.

### Changed

- 검색 캐시(`_detail_cache`·`_id_resolution_cache`) maxsize 50→64 — 규정 확대(N=36) 선제 마진(N=36은 50 미초과이나, 차기 확대·warm-hit 무력화(N>50) 대비). in-memory 상수만 변경, 동시성 모델·응답 schema·검색 거동 불변.

## [0.3.0] - 2026-06-20

**보건복지부 R&D 규정 지원 + 미지원 규정 현행성 정직 가드** — v0.2.12 라이브 eval에서 보건복지부 보건의료기술 R&D 운영규정이 미지원이라 일반 학습지식(2년 묵은 고시)으로 답해진 현행성 갭을, 데이터(보건복지부 family 등록)와 프롬프트(미지원 규정 현행 식별자 단정 자제)로 양면 대응한다. 단일 의도(현행성 갭 대응), 데이터+프롬프트+테스트만(서버 request 메커니즘·응답 schema 불변), `contract_version` **0.6.0 유지**. 지원 규정 **28 → 32개**.

### Added

- **보건복지부 보건의료기술 R&D family 4건**: 보건의료기술 진흥법(MST 279703)·시행령(282961)·시행규칙(264101)·보건의료기술 연구개발사업 운영·관리규정(admrul 2100000233560). 전건 LIVE 검증(2026-06-20)·표준 중첩 schema. 운영규정 표준협약서(별지 1, 23,082자)는 별지구분이라 BP·검색 미노출(본문은 source_url 공식 첨부 확인); BP 노출 별표는 BP0001·BP0002 2건(모두 본문 전문).
- `review_regulation` 템플릿·README 지원 규정 목록에 보건의료 R&D family 추가, 도구 prompt·플러그인·마켓플레이스 description에 보건복지부/보건의료 도메인 반영.

### Changed

- **범위 외 정직성 강화**: 서버 instructions에서 미지원 규정(도구 호출 결과 지원 32개 밖)을 일반 학습지식으로 설명할 때, 고시번호·시행일·조문 번호·금액·비율·기한 등 변동 가능한 구체값을 현행 사실로 단정하지 말고 1차 출처(국가법령정보센터 등)에서 확인하도록 안내(v0.2.12 잔여 결함 — scope-honesty 발화 후에도 stale 식별자를 단정하던 문제 봉쇄). 지원 규정 카운트 28→32 동기화.

## [0.2.12] - 2026-06-20

**도구 미가용 시 fail-closed 안내 + 범위 외 정직성** — v0.2.11 배포 후 라이브 eval(claude.ai 웹)에서, 한 대화의 세 번째 규정 질문에 호스트가 도구를 불러오지 못하고(host-side·다중 커넥터+컨텍스트 압박) 일반 학습지식으로 규정 수치·결론을 단정하는 컴플라이언스 위험을 확인. 서버 코드로 호스트의 도구 로딩을 강제할 수는 없으므로(MCP 한계), 도구가 빠졌을 때 잘못된 단정을 줄이는 안전장치와 안정적 사용 안내를 추가한다. 단일 의도, **텍스트/문서만**(코드 로직·응답 schema·검색·transport·외부 URL 불변), `contract_version` **0.6.0 유지**. ★이 릴리스는 호스트의 도구 로딩을 "고치는" 것이 아니라 도구가 빠졌을 때의 피해를 줄이는 안내임.

### Changed

- **서버 instructions에 fail-closed 분기 추가**: 규정 도구가 보이지 않거나 호출에 실패하면, 일반 학습지식으로 규정 수치·요건·결론을 단정하지 말고 도구 미가용을 알린 뒤 새 대화/Claude Desktop·Claude Code(stdio)로 재시도하도록 안내(기존 "도구 우선 호출" 신호는 그대로 유지).
- **범위 외 정직성**: 도구 호출 결과 질문 대상이 지원 28개 규정 밖이면, 본 서버 근거로 확인되지 않았음을 밝히고 일반 학습지식임을 명시하며 1차 출처 확인을 권하도록 안내(`도구 호출 결과` 기준 — 호출 전 추측으로 미지원 단정 방지).

### Added

- **README "안정적으로 사용하기" 안내**: claude.ai 웹에서 사용하지 않는 커넥터 끄기·인용(provision_id) 없는 답은 새 대화에서 재질의·중요한 검토는 Claude Desktop/Code(stdio)·지원 28규정 범위 명시.

### Unchanged

- `review_regulation` 프롬프트·검색/랭킹/fallback·응답 schema·외부 접속 URL(`https://mcp.rndmanagers.org/mcp?oc=<KEY>`)·`contract_version` 0.6.0.

## [0.2.11] - 2026-06-19

**HTTP 멀티테넌트 키 보호 + 공식 MCP Registry 등록 마커** — 첫 공식 홍보(MCP Registry 등록) 준비. 단일 실질 의도 = HTTP 멀티테넌트 키 보호. 원격(HTTP) 커넥터 호출에 `?oc=` 키가 없으면 이전에는 서버 env 키(운영자 키)로 silent fallback하여 과금·감사가 누출될 수 있었다 — 이를 **HTTP 한정**으로 차단하고 표준 오류 `auth_failed`를 반환한다. stdio(Claude Desktop·uvx)는 env 키가 정상 경로이므로 `_is_http_request` 기본 False로 **거동 불변(무회귀)**. 응답 schema·필드·shape·검색/랭킹/fallback 알고리즘·외부 접속 URL 불변, `contract_version` **0.6.0 유지**(신규 필드·오류코드 없음 — 기존 `auth_failed` 오류경로 강화). 마커·`server.json`은 런타임 무관 additive. 3-AI 적대검증(구현안) blocking 0.

### Security

- **HTTP no-oc 키 보호**: `?oc=` 없는 HTTP 요청을 server env 키로 처리하지 않고 `auth_failed`(원격 호출에는 `?oc=` 필요 안내)로 차단. `_is_http_request` contextvar로 transport를 구분하여 stdio(env 키 정상 경로)에는 영향 없음. `_get_client`에서 raise하지 않고(호출부가 try/except 밖이라 uncaught crash 방지) 3개 도구(`search_provision`·`get_provision_detail`·`suggest_review_sources`) 진입부에서 구조화된 오류를 early-return.
- **access log 키 차단(근본 수정)**: `--http` 서버의 uvicorn access log가 요청 라인에 `?oc=` 키를 기록하던 것을 `uvicorn_config={"access_log": False}`로 코드 레벨에서 차단(기존 compose `FASTMCP_LOG_LEVEL=WARNING` 억제는 유지 — 이중 방어).

### Added

- **공식 MCP Registry 등록 마커**: `README.md` 최상단에 `<!-- mcp-name: io.github.smilemin07/korean-rnd-regs-mcp -->`(PyPI description 소유권 검증용) + repo 루트 `server.json`(PyPI 패키지 등록용·`remotes` 제외=호스팅 endpoint 미노출로 키 안전). 런타임·응답 동작과 무관.

### Unchanged

- 지원 규정 28개·검색/랭킹/fallback·응답 schema·외부 접속 URL(`https://mcp.rndmanagers.org/mcp?oc=<KEY>`)·`contract_version` 0.6.0.

## [0.2.10] - 2026-06-18

**검색 fan-out 지연 관측성 (B1 — 스태빌리티 트랙 1단계)** — v0.2.9로 "도구 호출 유도"가 완료되어, Andy의 최우선 가치(서비스 끊김 회피)에 따라 스태빌리티 트랙으로 회귀. 진짜 outage 위험은 NAS 4코어 = 전역 8스레드 풀(`asyncio.to_thread` 기본 executor) 고갈이나, 이를 고치려면(B2 전용 executor) 풀 크기 N을 알아야 하는데 현재 그 데이터(규정별·전체 fan-out 소요 시간)가 측정되지 않는다. 추정 N으로 풀을 도입하면 정상 요청까지 끊는 self-outage가 되므로 **"측정 먼저, 고치기 나중"**이 끊김 회피 원칙에 부합. 본 버전은 **서버 측 로그(stderr)만 추가**한다 — 코드 동작·네트워크 호출 방식·응답 schema를 전혀 바꾸지 않으며(응답 신규 필드 0), `contract_version` **0.6.0 유지**. 단일 의도 = 관측성. 3-AI 적대검증 2라운드(범위 결정 + 구체 구현안, 각 blocking 0).

### Added

- **fan-out 요약 로그** (`search_provision`, INFO·key=value): fan-out 1회당 `event=search_fanout_summary` 한 줄로 `live_rules`·`done`·`skipped`·`wall_ms`·`budget_ms`·`max_rule_ms`·`slow_rule_count`·`errors_count` 기록. 진단: `wall_ms ≫ max_rule_ms`이면 8스레드 풀 큐잉(B2 격리 필요), 근사하면 네트워크 지연 우세(B2는 속도보다 격리 목적).
- **규정별 지연 로그** (`search_provision`, **DEBUG**): 규정마다 `event=fanout_rule rule_set_id=… api_target=… status=… elapsed_ms=…`. 반드시 DEBUG — `suggest_review_sources` 1회가 최대 ~16 검색 × 28 규정을 유발하므로 INFO면 운영 로그가 폭주(가용성 위협). 기본 `LOG_LEVEL=INFO`에서는 출력되지 않음.
- **suggest 요약 로그** (`suggest_review_sources`, INFO): `event=suggest_search_summary keyword_source=… search_calls=… wall_ms=… errors_count=… candidates_count=…`. suggest 1회가 유발한 내부 `search_provision` 호출 수(숨은 부하 증폭)를 가시화.
- **상수 `_SLOW_RULE_MS=3000.0`**: 개별 규정 지연이 이 값(ms) 이상이면 `slow_rule_count`로 집계(B2 N 산정용 tail 휴리스틱). 예산 초과로 skip된 규정의 실제 스레드 완료 시간은 미포함(완료 task 기준 집계).
- **관측성 가드 테스트 2건** (`tests/test_tools.py`): 요약 로그(INFO)·per-rule 로그(DEBUG)가 출력되고 레벨이 정확한지 + 신규 로그에 OC 키·요청 URL이 미포함됨(시크릿 안전)을 결정적으로 검증.
- **배포 전 LIVE acceptance spec** (`tests/acceptance/v0_2_10.py`): Level A는 로그 추가가 v0.2.9 검색을 회귀시키지 않았는지(광역 '연구개발비' 최상위·대형 규정 도달·recall·지연)만 확인하는 순수 회귀 가드. Level B는 배포 후 사람이 NAS 컨테이너 로그를 grep해 fan-out 지표를 확인하고 B2 착수 신호(`skipped>0`·`wall_ms>=15000`)를 판독하는 절차.

### Security

- 신규 로그 3종은 OC 키·요청 URL·`query`·`keywords`·예외 message를 포함하지 않음(rule_set_id 식별자·정수 지표·예외 클래스명만). `live_api`의 "예외는 type 이름만 로깅" 원칙과 동일. 회귀 테스트로 강제.

### Unchanged (additive — 회귀 가드)

- 검색 매칭·관련도 정렬(v0.2.8)·suggest 랭킹·fallback 추출기·fan-out 응답 예산(20s)·timeout 상한·동시성 모델(`asyncio.to_thread` 기본 executor) **불변**.
- 응답 schema·필드·표준 오류 코드·provision_id 포맷 **불변** → `contract_version` **0.6.0 유지**(신규 로그는 서버 측 stderr만이며 도구 응답에 미노출).
- 지원 규정 **28개**·외부 접속 URL(`https://mcp.rndmanagers.org/mcp?oc=<KEY>`) **불변**.
- 테스트 **227**(직전 224 + 관측성 가드 2 + acceptance spec 파라미터화 1).

## [0.2.9] - 2026-06-17

**규정 질의 도구 호출 유도 — 메타데이터 가드** — v0.2.8 배포 후 라이브 eval(Sonnet 4.6)에서, 광역 "연구개발비 폭넓게 알려줘" 질의에 호스트가 **MCP 도구를 호출하지 않고 훈련 지식으로 답해** 근거 없는 단정(soft-fabrication)을 내는 것이 확인됨 — 규정 검토 도구의 최악 실패 모드이며, v0.2.0~0.2.8 검색 품질 개선 전체를 무효화하는 상위 변수. 이를 **메타데이터(텍스트)만**으로 억제: 서버 레벨 `instructions` 신설 + 3개 도구 docstring 첫 문단에 "사용 시점/호출 금지" 스탠자 추가. 호스트가 본 서버 범위의 규정 질의에는 일반 지식 대신 도구를 먼저 호출하도록 유도하고, 단순 대화·범위 밖 질의에는 호출하지 않도록(과호출 차단) 안내. 검색·랭킹·fallback·응답 schema·외부 URL·지원 규정 28개 모두 불변. `contract_version` **0.6.0 유지**(응답 schema 무변). 변경의 핵심(서버 instructions)은 MCP initialize 응답 payload에 실리므로 배포 전 로컬·신 이미지 부팅 스모크 필수. 단, 도구 호출은 호스트 하니스가 좌우하는 비결정(Level B) 영역이라 본 변경은 "확정 해결"이 아니라 가장 낮은 outage 위험으로 거는 신호 보강이며, 실효는 배포 후 수동 eval로 측정. ultracode 워크플로 + 외부 2-AI 적대검증(/disc, blocking 0).

### Changed

- **서버 레벨 `instructions` 신설** (`main.py`): `FastMCP(..., instructions=_SERVER_INSTRUCTIONS, version=__version__)`. 호스트가 규정 질의에 일반 학습지식으로 단정하지 말고 `suggest_review_sources`/`search_provision`을 먼저 호출하고 근거는 `get_provision_detail`로 확인하도록 유도. 과호출 방지를 위해 적용 범위를 "본 서버 범위(대한민국 R&D 연구행정 규정)"로 한정하고 WHEN-NOT 절(단순 인사·순수 번역·문장 다듬기·코딩·해외 제도) 명시. 광역 "폭넓게 알려줘" 표현도 규정 사실 확인이면 호출 대상임을 명문화.
- **3개 도구 docstring 첫 문단에 "사용 시점/호출 금지" 스탠자 추가** (`search_provision`·`suggest_review_sources`·`get_provision_detail`): 서버 `instructions`를 주입하지 않는 호스트 대비 이중화. 기존 docstring 본문은 그대로 보존(스탠자 prepend). `get_provision_detail` 스탠자에 "provision_id의 원문·삭제 여부·현행 내용을 확인" 일반 문구를 둬, 일부 조문(예: 연구개발비 사용 기준 제30조 인력지원비·제31조 연구지원비)이 현행 개정으로 삭제·이동된 사실을 **조문 번호 하드코딩 없이** 호스트가 detail 호출로 직접 확인하도록 유도(특정 조문 상태를 prompt/data에 박지 않음 = stale 위험 회피).
- **결정적 가드 테스트 3건 추가** (`tests/test_main.py`): 서버 `instructions` 탑재·핵심 구절 포함 / 3개 도구 docstring 도구별 핵심 구절 포함 / `contract_version == "0.6.0"` 유지. 동작(호출 여부)이 아니라 "문구 탑재"만 결정적으로 검증(behavior는 Level B 수동 eval 몫). 긴 문장 verbatim이 아닌 짧고 안정적인 키 구절만 단언(유지보수 churn 회피).
- **배포 전 LIVE acceptance spec 추가** (`tests/acceptance/v0_2_9.py`): Level A는 메타데이터 변경이 v0.2.8 검색을 회귀시키지 않았는지(광역 '연구개발비' 최상위·대형 규정 도달·recall)만 확인하는 회귀 가드. Level B 프롬프트 세트를 positive(광역 "~알려줘" → 도구 호출 기대) + negative(인사·번역·해외 제도 → 미호출 기대, 과호출 차단 검증)로 확장 — 배포 후 사람이 진짜 호스트에서 수동 eval.

### Unchanged (additive — 회귀 가드)

- 검색 매칭(토큰 AND)·관련도 정렬(v0.2.8)·suggest 랭킹·fallback 추출기·fan-out 응답 예산(20s)·timeout 상한 **불변**.
- 응답 schema·필드·표준 오류 코드·provision_id 포맷 **불변** → `contract_version` **0.6.0 유지**.
- 지원 규정 **28개**·외부 접속 URL(`https://mcp.rndmanagers.org/mcp?oc=<KEY>`) **불변**.
- 테스트 **224**(직전 220 + 가드 3 + acceptance spec 파라미터화 1).

## [0.2.8] - 2026-06-17

**검색 결과 관련도 정렬 — 광역 질의 매몰 방지** — 자연어로 여러 규정을 한 번에 검색하는 광역 질의에서, 응답 크기 한도(16k char)로 뒤쪽 결과가 잘리는데 종전에는 결과가 규정 목록(manifest) 순서로만 쌓여 **질문과 가장 관련 높은 규정이 앞순위 규정에 자리를 빼앗겨 잘려나가는** 문제가 있었음(v0.2.7 배포 후 라이브 점검: 광역 "연구개발비" 질의 시 정작 핵심인 「국가연구개발사업 연구개발비 사용 기준」이 결과에서 누락). 결과를 **절단 직전에 관련도 순으로 정렬**하여 문서 제목이 질문과 직접 일치하는 규정이 먼저 보이도록 함. 응답 형식·필드·검색 매칭 알고리즘·외부 URL·지원 규정 28개 모두 불변. `contract_version` **0.6.0 유지**(결과 표시 순서는 계약 보장 항목이 아니며 schema 무변 — 선례 v0.1.6·v0.1.7). 변경은 요청 경로 한정으로 서버 부팅·HTTP transport 비의존. ultracode 워크플로 + 외부 2-AI 적대검증(/disc, blocking 0).

### Changed

- **`search_provision` 결과 관련도 정렬**: `_RESULTS_MAX`(30건)·16k char 예산으로 결과를 자르기 *직전에* 각 결과를 결정적 관련도 정렬키로 재정렬. 우선순위 = ① 문서(규정) 제목 적중 토큰 수 → ② 조문·별표 제목 적중 → ③ 본문 적중(distinct 토큰, 대형 문서 편향 없음) → ④ 단위유형(조문 우선) → ⑤ 위계(법률>시행령>…) → ⑥ 기존 수집 순서(동률 시 현행 순서 보존·완전 결정성). 문서 제목 적중을 최상위 신호로 둬, 규정 목록 후순위지만 제목이 직접 일치하는 핵심 규정이 절단에서 생존. (`_relevance_sort_key`)

### Unchanged (안전)

- 응답 schema·필드·shape, 검색 토큰 매칭(`_content_matches`)·snippet·fallback·fan-out 응답 예산(20s)·외부 API timeout·`timeout` 오류코드, 지원 규정 28개, 외부 접속 URL 모두 불변. 정렬키·관련도 점수는 응답에 노출하지 않음(신규 필드 0). 기존 테스트 0건 파손, 신규 단위 테스트 6건 + acceptance 가드 1건 추가(총 220).

## [0.2.7] - 2026-06-14

**구동 안정성 강화 — 외부 API 대기 상한 보수화** — 검색 시 28개 규정을 동시에 조회(fan-out)하는 과정에서, 응답이 느린 일부 요청이 백그라운드 작업자(스레드)를 오래 점유해 동시 질의가 쌓이면 전체가 지연될 수 있는 잠재 위험을 보수적으로 차단. 외부 OpenAPI 대기 시간 상한을 `(connect 8s, read 12s)`로 분리하고 재시도를 3→2회로 줄여 단일 규정의 worst-case 스레드 점유를 약 186s → 82s로 단축. fan-out 응답 예산(20s)은 유지(부등식 read 12s < 예산 20s < 커넥터 타임아웃 정합). 검색·랭킹·응답 schema·외부 URL·지원 규정 28개 모두 불변. `contract_version` **0.6.0 유지**(내부 거동 보수화·schema 무변). 변경은 요청 경로 한정으로 서버 부팅·HTTP transport 비의존. ultracode 워크플로 + 외부 2-AI 적대검증(/goal-disc-out, blocking 0).

### Changed

- **외부 API 요청 timeout 분리·단축**: 정수 `30s`(connect·read 공통) → `(connect 8s, read 12s)` 튜플. 정상 규정 조회(detail 평시 0.6~1.3s)에 충분한 여유를 두면서, 응답 지연 요청을 빨리 포기시켜 스레드 점유를 bound. (`_CONNECT_TIMEOUT_S`·`_READ_TIMEOUT_S`·`_REQUEST_TIMEOUT` 상수)
- **재시도 축소**: `max_retries` 3 → 2 (일시적 5xx 내성은 유지하되 worst-case 점유 절감). (`_MAX_RETRIES` 상수)
- **graceful skip 안내 문구 정제**: 응답 예산 초과로 제외된 규정 안내를 '끊김/생략'이 아닌 '부분 결과 — 서비스 중단이 아니며 키워드를 좁혀 다시 검색' 신호로 변경(체감 안정성).

### Notes

- fan-out 응답 예산(`_FANOUT_BUDGET_S` = 20s)은 *유지* — 예산은 사용자 응답만 풀고 진행 중인 백그라운드 요청은 못 끊으므로, 실제 대기 상한은 위 timeout 보수화가 보장한다(주석으로 문서화).
- 연결 풀(Session 재사용)·전용 스레드 풀·소관부처 카탈로그 완성·지원 규정 확대는 본 릴리스 범위 밖(이후 버전에서 단계적).

## [0.2.6] - 2026-06-13

**지원 규정 재편 2차 — 과기정통부 R&D 연구자 빈출 규정 (25→28개) + 소관부처 resolve 필터** — 과학기술정보통신부 소관 R&D에 참여하는 연구자가 참조하는 핵심 규정 9건을 추가하고, R&D 행정과 거리가 먼 보조 법령 6건(부패방지·청탁금지·공익신고자보호)을 정리. 동명 규정이 복수 부처에 존재할 때(예: 기술료 통합요령) 자부처 현행본만 정확히 조회하는 소관부처 필터를 도입. 전 신규 항목 LIVE 검증(2026-06-13) 식별자·시행일로 등록. 외부 2-AI 적대검증(/disc·/goal-disc-out, blocking 0) 후 단일 release로 통합. `contract_version` 0.5.0 → **0.6.0**(`list_rule_sets` 응답에 `ministry` 필드 additive 추가). 코드는 부팅·HTTP transport 비의존(outage 무위험).

### Added

- **성과평가 family (2건)**: 국가연구개발사업 등의 성과평가 및 성과관리에 관한 법률(MST 255639)·시행령(270435)
- **공통 행정규칙 (5건)**: 국가연구개발정보처리기준(2100000195842)·국가연구개발사업 보안대책(2100000231472)·과학기술정보통신부 소관 과학기술분야 연구개발사업 처리규정(2100000228284)·정보통신·방송 연구개발 관리규정(2100000258836)·정보통신·방송 연구윤리 진실성 확보 등에 관한 규정(2100000248908)
- **기술료 family (2건)**: 기술료 징수 및 관리에 관한 통합요령(산업통상부, 2100000257278)·중소기업기술개발 지원사업 기술료 관리규정(중소벤처기업부, 2100000276844)
- **소관부처 필터**(`RuleSet.ministry` + `resolve_latest_doc_id`): 검색 행 소관부처명을 콤마 분리·정확일치로 비교해 동명 타부처 규정 오집을 차단(기술료 통합요령이 기후에너지환경부 동명으로 잘못 resolve되던 문제 해소). `ministry` 미기재 규정(기존 19건)은 거동 불변.
- `list_rule_sets` 응답에 `ministry` 필드 추가(additive — contract 0.6.0).

### Changed

- **search_provision fan-out 응답 시간 예산(20초) 가드**: 한 규정의 상세 조회가 지연(법령정보 서버 응답 지연·재시도 폭주)되어 전체 검색이 커넥터 타임아웃까지 멈추는 것을 차단. 예산 초과 규정은 graceful skip하여 `errors`(code `timeout`)로 표면화하고 완료된 결과로 응답(부분 응답 > 전체 실패). 정상 조회(전건 완료, 통상 수 초)는 예산 한참 아래라 무영향. 대형 행정규칙(정보통신·방송 관리규정 등) 추가로 cold 응답 시간이 늘어난 데 대한 가용성 안전 가드.
- 별표 외 부속문서 조회 불가 안내를 별지·서식 하드코딩에서 **비'별표' 전 종류(별첨·붙임 포함) 일반화** — 신종 별표구분이 안내 없이 누락되던 갭 해소.
- review_regulation 프롬프트 "MCP 적용 범위" 절·도구 설명 25→28개 갱신 + README 임베드 동기화.

### Removed

- **보조 법령 6건 정리**: 부패방지 및 국민권익위원회의 설치와 운영에 관한 법률·시행령, 부정청탁 및 금품등 수수의 금지에 관한 법률(청탁금지법)·시행령, 공익신고자 보호법·시행령. 범용 법률로 본 서비스의 핵심 정체성(R&D 행정규정 verbatim 근거) 밖이며 광역 검색 노이즈를 유발 — 라인업에서 제외. 식별자는 보존하여 향후 실수요 확인 시 재등록 가능.

### Tests

- 신규 규정 등록·소관부처 필터·`list_rule_sets` ministry 필드·별첨/붙임 안내 일반화 + 삭제 6건 연쇄 정리. contract 0.6.0 정렬.

## [0.2.5] - 2026-06-13

**지원 규정 확대 1차 — 3부처 R&D (17→25개) + 검색 응답 예산 가드** — 과기부(기존 커버)·산업부·중소벤처기업부 공고 R&D 참여 연구자가 참조하는 핵심 규정 8건을 추가. 전 항목 LIVE 검증(2026-06-12) 식별자·시행일로 등록. 확대로 광역 질의 응답이 40k+자(25k token 한도 초과 위험)로 실측됨에 따라 `search_provision` 전체 응답 16k char 예산을 동승 도입. `contract_version` **0.5.0 유지**(응답 schema·필드 무변 — 기존 `returned`/`truncated` 필드가 절단 신호).

### Added

- **산업기술 R&D family (4건)**: 산업기술혁신 촉진법(MST 280041)·시행령(285891, 별표 4)·시행규칙(286385, 별표 5·서식 15)·산업기술혁신사업 공통 운영요령(2100000251982, 평면 schema·조문 53·별표 7·서식 9)
- **중소기업 R&D family (4건)**: 중소기업 기술혁신 촉진법(MST 286263)·시행령(283001, 별표 4)·시행규칙(220365)·중소기업기술개발 지원사업 운영요령(2100000273462, 평면 schema·조문 51·별표 3)
- review_regulation 프롬프트 "MCP 적용 범위" 절에 두 family 추가(17→25개 규정) + README 임베드 동기화

### Changed

- **search_provision 전체 응답 char 예산(16k)**: 직렬화 누적이 예산을 넘으면 뒤쪽 결과 절단(최소 1건 보장·manifest 순서 유지). LIVE 실측 — "간접비" 41.7k→14.5k, "기술료" 45.5k→14.6k, 핀포인트 질의("서울대학교" 등)는 무영향. 광역 질의는 `truncated=true` 신호를 보고 키워드를 좁혀 재검색(docstring 안내 추가)

### Tests

- 25개 manifest id·count 검증 갱신 + 응답 예산 가드 1건 추가 + mock cap 초과 환경 보정 2건. 전체 196 → **197**.

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
