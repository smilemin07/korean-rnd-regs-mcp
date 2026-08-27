"""66규정 전체의 "다가오는 시행 예정 판본" 검출 — 달력 의존 제거용 감사 스크립트.

(2026-08-27 신설 · 계획 3-AI /disc 3/3 합의 · 구현 diff 적대검토 Codex+Gemini 조건 반영)
기존 감사 2종은 방향이 반대다: audit_manifest_effective_dates.py는 "이미 등록한 ID가
미시행 본문을 서빙 중인가"를, audit_law_stage_diff.py는 "공포 합본 vs 시행 본문 차이"를
본다. 둘 다 "현행 규정에 새 시행분이 다가오고 있는가"(예: 2026-09-11 혁신법 283849·
시행령 288335 도래)는 검출하지 못해, 지금까지는 rule_sets.yaml 주석과 사람의 달력 기억에
의존했다. 본 스크립트가 그 빈 방향을 메운다.

조회 경로(검색 행 기준 — C12 규칙: 상세응답 시행일자 채택 금지):
  law    : lawSearch target=eflaw&query=<제목> (nw 미지정 = 현행·연혁·시행예정 전 행)
           → 제목 정확일치 행 중 시행일자 > 오늘(KST)인 행 = 시행 예정.
           target=law&nw=2는 타법개정 누락(불완전·2026-08 실측)이라 쓰지 않는다.
  admrul : lawSearch target=admrul&query=<제목> → 동일 필터. ★한계(정직 선언):
           행정규칙은 eflaw 비상응이라 API가 시행 전 행을 검색에 등재할 때만 검출된다.
           admrul의 NONE은 "오늘 검색에 미래 행이 보이지 않음"이지 "예정 없음 보증"이 아니다.
  ★부처 필터: manifest에 ministry가 기재된 규정만 소관부처 정확일치 필터를 적용한다.
           미기재 규정(현재 19건)은 제목 정확일치만 적용 — 동명 타부처 규정이 실재하면
           그 행도 집계될 수 있다(과소가 아니라 과잉 방향이므로 경보 도구로는 안전측).

판정(3분류 — fail-closed·우선순위 UPCOMING > UNKNOWN > NONE):
  UPCOMING : 유효한 미래 시행일자 행 존재(당일 시행은 현행 취급 — _is_future_date 규약).
             → 달력 등록·해당 일자 재감사 준비 (경보이며 오류 아님).
  NONE     : 매칭 행 1건 이상 + 미래 행 0건 + 날짜 이상 행 0건.
  UNKNOWN  : 조회 실패 / 매칭 행 0건(제목·부처 변경 가능성) / 시행일자 형식·달력 무효 행
             존재 / 검색 절단·페이지 갭. 확인 실패를 "예정 없음"으로 격하하지 않는다.

fail-closed 장치:
  - 페이지 상한 도달·중간 빈 페이지(seen < total)는 부분 성공이 아니라 예외 → UNKNOWN.
  - 연속 3규정 조회 실패 시 공통 장애(네트워크·인증·호출 제한)로 보고 즉시 중단 —
    잔여 규정을 NONE으로 오인할 기회 자체를 없앤다. 규정별 결과는 실시간 출력.

종료 코드: 0 = 전건 NONE / 3 = UPCOMING 존재(사람 확인) / 2 = UPCOMING 없음·UNKNOWN
(또는 중단·미실행) 존재.

사용(read-only — manifest·코드를 수정하지 않는다):
  /Users/andykim/my_project/venv/bin/python scripts/audit_upcoming_enforcement.py            # 전체
  /Users/andykim/my_project/venv/bin/python scripts/audit_upcoming_enforcement.py innovation_act ...  # 지정만

보안: 키(LAW_API_KEY/OC)는 어떤 형태로도 출력하지 않는다(예외 본문도 출력하지 않음).
검색 행의 `…링크` 필드(API가 OC 키 원문을 삽입)는 읽지 않는다 — 아래 화이트리스트 필드만 접근.
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# 링크 필드 배제 화이트리스트 (audit_law_stage_diff.SAFE_ROW_FIELDS와 동일 규약)
LAW_ROW_FIELDS = ("법령ID", "법령일련번호", "법령명한글", "소관부처명", "시행일자",
                  "공포일자", "공포번호", "제개정구분명", "현행연혁코드", "자법타법여부")
# 발령일자·발령번호 = 2026-08-27 라이브 실측 필드명. 제정일자는 live_api 기존 파서와의
# 호환 표기로 함께 둔다(부재 시 빈 문자열 — 판정은 시행일자만 사용).
ADMRUL_ROW_FIELDS = ("행정규칙일련번호", "행정규칙ID", "행정규칙명", "소관부처명",
                     "발령일자", "발령번호", "제정일자", "시행일자", "현행연혁구분", "제개정구분명")
_SEARCH_DISPLAY = 100
_PAGE_CAP = 10        # 제목 정확일치 검색이 1,000행을 넘으면 그 자체가 이상 신호
_CONSEC_ERR_ABORT = 3  # 연속 실패 회로차단 임계(공통 장애 의심)


def _valid_date(raw: str | None) -> bool:
    """8자리 숫자 + 달력 유효(월 13·2월 31 배제). 하이픈·공백 정규화."""
    d = (raw or "").strip().replace("-", "")
    if len(d) != 8 or not d.isdigit():
        return False
    try:
        time.strptime(d, "%Y%m%d")
    except ValueError:
        return False
    return True


def _norm_date(raw: str | None) -> str:
    return (raw or "").strip().replace("-", "")


def classify_rows(rows: list[dict], today: str, fetch_error: bool = False) -> tuple[str, list[dict], int]:
    """순수 함수(단위 테스트 대상: tests/test_audit_upcoming.py).

    반환 = (판정, 미래 행 목록[일련번호+시행일자 중복 제거·시행일자 오름차순], 날짜 이상 행 수).
    우선순위: 조회 실패 → UNKNOWN / 유효 미래 행 → UPCOMING(이상 행이 있어도 경보가 우선)
    / 이상 행 존재 → UNKNOWN / 매칭 0건 → UNKNOWN / 그 외 → NONE.
    당일 시행(시행일자 == 오늘)은 현행이므로 미래가 아니다.
    일련번호 누락 행은 중복 제거하지 않고 전부 보존한다(식별 불가 행끼리 합치지 않음).
    """
    if fetch_error:
        return "UNKNOWN", [], 0
    today = _norm_date(today)  # 방어 정규화(diff 적대검토): 하이픈 today가 문자 비교를 오염시키지 않게
    future, anomalies, seen = [], 0, set()
    for r in rows:
        raw = r.get("시행일자")
        if not _valid_date(raw):
            anomalies += 1
            continue
        d = _norm_date(raw)
        if d > today:
            serial = r.get("법령일련번호") or r.get("행정규칙일련번호") or ""
            if serial:
                key = (serial, d)
                if key in seen:
                    continue
                seen.add(key)
            future.append(r)
    future.sort(key=lambda r: _norm_date(r.get("시행일자")))
    if future:
        return "UPCOMING", future, anomalies
    if anomalies:
        return "UNKNOWN", [], anomalies
    if not rows:
        return "UNKNOWN", [], 0
    return "NONE", [], 0


def exit_code(counts: dict) -> int:
    """순수 함수. UPCOMING > UNKNOWN > 전건 NONE. 집계 0건은 '전건 NONE'이 아니라 2."""
    total = sum(counts.get(k, 0) for k in ("UPCOMING", "NONE", "UNKNOWN"))
    if counts.get("UPCOMING", 0):
        return 3
    if counts.get("UNKNOWN", 0) or total == 0:
        return 2
    return 0


def _fetch_rows(client, rs) -> list[dict]:
    """규정 1건의 검색 행 수집 — 제목 정확일치(+ministry 기재 시 부처 정확일치).

    링크 필드는 읽지 않는다. 페이지 무결성 위반(중간 빈 페이지·상한 도달 시 미탐색 잔존)은
    부분 성공으로 돌려주지 않고 예외 → 호출부 UNKNOWN (fail-closed·diff 적대검토 Codex MAJOR 1).
    """
    from korean_rnd_regs_mcp.live_api import _parse_xml, _request_with_retry

    is_law = rs.api_target.value == "law"
    target = "eflaw" if is_law else "admrul"
    item_tag = "law" if is_law else "admrul"
    title_tag = "법령명한글" if is_law else "행정규칙명"
    fields = LAW_ROW_FIELDS if is_law else ADMRUL_ROW_FIELDS
    norm = client._normalize_title(rs.title)
    rows, page, seen = [], 1, 0
    while True:
        resp = _request_with_retry(f"{client.base_url}/lawSearch.do", {
            "OC": client.api_key, "type": "XML", "target": target, "query": rs.title,
            "display": _SEARCH_DISPLAY, "page": page,
        })
        root = _parse_xml(resp)
        total = int(root.findtext(".//totalCnt", "0") or "0")
        items = root.findall(f".//{item_tag}")
        for e in items:
            if client._normalize_title(e.findtext(title_tag, "") or "") != norm:
                continue
            if not client._ministry_matches(rs.ministry or "", e.findtext("소관부처명", "") or ""):
                continue
            rows.append({t: (e.findtext(t, "") or "").strip() for t in fields})
        seen += len(items)
        if not items:
            if seen < total:
                # 중간 빈 페이지 = 미탐색 행 잔존 — 부분 행으로 NONE을 만들지 않는다
                raise RuntimeError(f"search_page_gap: total={total} seen={seen} page={page}")
            break
        if seen >= total:
            break
        if page >= _PAGE_CAP:
            # fail-closed: 미탐색 행에 미래 행이 있을 수 있으므로 절단을 NONE으로 격하하지 않는다
            raise RuntimeError(f"search_truncated: total={total} seen={seen} (page cap {_PAGE_CAP})")
        page += 1
    return rows


def main(argv: list[str]) -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not bool(os.environ.get("LAW_API_KEY")):
        print("LAW_API_KEY 미설정 — .env를 확인하십시오 (값은 출력하지 않습니다).")
        return 2
    from korean_rnd_regs_mcp.live_api import LawApiClient
    from korean_rnd_regs_mcp.manifest import Retrieval, load_manifest

    only = set(argv)
    items = [rs for rs in load_manifest() if rs.retrieval == Retrieval.LIVE_API]
    # fail-closed: 미인식 ID·대상 0건이 "전건 NONE"으로 헛통과하지 않게 네트워크 호출 전 차단.
    unknown_ids = only - {rs.id for rs in items}
    if unknown_ids:
        print(f"지정 rule_set_id 미인식: {', '.join(sorted(unknown_ids))} — 오타 확인 후 재실행 (fail-closed).")
        return 2
    targets = [rs for rs in items if not only or rs.id in only]
    if not targets:
        print("감사 대상 0건 — 지정 조건을 확인하십시오 (fail-closed).")
        return 2

    client = LawApiClient()
    today = client._today_kst()
    counts = {"UPCOMING": 0, "NONE": 0, "UNKNOWN": 0}
    upcoming_detail = []
    consec_err, aborted_remaining = 0, 0
    print(f"기준일(오늘·KST): {today}", flush=True)
    for idx, rs in enumerate(targets):
        rows, err = [], False
        try:
            rows = _fetch_rows(client, rs)
        except Exception:
            err = True  # 예외 본문은 출력하지 않는다(키·URL 잔존 가능성 원천 차단)
        verdict, future, anomalies = classify_rows(rows, today, fetch_error=err)
        counts[verdict] += 1
        note = "(조회 실패)" if err else (f"(날짜 이상 행 {anomalies})" if anomalies else "")
        if verdict == "UNKNOWN" and not err and not anomalies and not rows:
            note = "(매칭 행 0건 — 제목·부처 변경 가능성)"
        if verdict == "NONE" and not err and rs.api_target.value == "admrul":
            note = "(검색 가시 범위 한정 — 비보증)"
        shown = "?" if verdict == "UNKNOWN" else str(len(future))  # 확인 불가는 0이 아니라 ?
        print(f"{verdict:8} | {rs.id:32} | {rs.api_target.value:6} | 미래 행 {shown} {note}", flush=True)
        for r in future:
            serial = r.get("법령일련번호") or r.get("행정규칙일련번호") or "?"
            pub = r.get("공포일자") or r.get("발령일자") or r.get("제정일자") or "?"
            pub_no = r.get("공포번호") or r.get("발령번호") or ""
            kind = r.get("제개정구분명") or r.get("현행연혁구분") or ""
            upcoming_detail.append(
                f"  → {rs.id}: 일련번호 {serial} · 시행 {r.get('시행일자')} · 공포/발령 {pub}"
                + (f" · 공포번호 {pub_no}" if pub_no else "") + (f" · {kind}" if kind else "")
            )
        consec_err = consec_err + 1 if err else 0
        if consec_err >= _CONSEC_ERR_ABORT:
            aborted_remaining = len(targets) - idx - 1
            print(f"중단: 연속 {consec_err}규정 조회 실패 — 공통 장애(네트워크·인증·호출 제한) 의심. "
                  f"잔여 {aborted_remaining}건 미실행 (fail-closed — NONE으로 간주하지 말 것).", flush=True)
            break
    if upcoming_detail:
        print("\n시행 예정 상세:")
        for ln in upcoming_detail:
            print(ln)
    ran = sum(counts.values())
    print(f"\n요약: UPCOMING {counts['UPCOMING']} / NONE {counts['NONE']} / UNKNOWN {counts['UNKNOWN']}"
          f" (실행 {ran} / 대상 {len(targets)}" + (f" · 미실행 {aborted_remaining}" if aborted_remaining else "") + ")")
    code = exit_code(counts)
    if aborted_remaining and code == 0:
        code = 2  # 미실행 잔존을 '전건 NONE'으로 반환하지 않는다
    if counts["UPCOMING"]:
        print("→ UPCOMING 존재: 해당 시행일을 달력에 등록하고, 그날 재감사(/regs-audit + audit_law_stage_diff)를 준비하십시오.")
    if counts["UNKNOWN"] or aborted_remaining:
        print("→ UNKNOWN(또는 미실행) 존재: 확인 불가 — 재실행 필요 (NONE으로 간주하지 말 것).")
    if code == 0:
        print("→ 전건 NONE: 오늘 검색 기준 시행 예정 판본 없음 (admrul은 검출력 비보증 — 상단 docstring 참조).")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
