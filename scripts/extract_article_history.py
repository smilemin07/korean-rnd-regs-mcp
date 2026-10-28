"""조문별 변경 이력 스냅샷 생성 — v0.60.0 「조문별 변경 이력 안내」 동반 도구(배포 전 실행·런타임 무관).

무엇을 만드는가(비프로그래머용): 서버가 법령 조문 상세 응답에 "이 조문이 마지막으로 바뀐 판본"을
알려 주려면 조문마다 국가법령정보 조문별 변경 이력(lawService target=lsJoHstInf)이 필요합니다.
요청할 때마다 조회하면 응답이 느려지고 장애 경로가 늘어나므로, 배포 전에 이 스크립트로 한 번 모아
`src/korean_rnd_regs_mcp/article_history.json`에 저장합니다. 서버는 이 파일만 읽습니다.

어떻게 고르는가(조문마다):
  1. 서버와 같은 resolve(LawApiClient.resolve_latest_doc_id)·같은 본문 조회(get_law_detail_staged)로
     서빙 판본(MST·시행일자)을 정한다. 본문이 시행일 기준(eflaw)이 아니면 그 법령은 수록하지 않는다.
  2. 이력 항목 중 시행일자 ≤ 서빙 시행일자인 최신 항목을 고른다. 같은 최신 시행일자에 공포번호가
     둘 이상이면 제외한다(어느 판본인지 정할 수 없음).
  3. 응답의 조문번호가 요청한 번호와 다르면 제외한다.
  4. 본문 이력 표지(latest_history, 공포일)와 대조한다. 표지가 있으면 그 공포일이 고른 항목의 공포일과
     같아야 한다. 표지가 없으면 변경사유가 제정·전부개정일 때만 수록한다. 삭제된 조문은 제외한다.
  5. 고른 항목의 판본(법령일련번호)이 시행 단계 표(lawSearch target=eflaw)에 있어야 하고, 시행일이 둘
     이상이면 분리 시행으로 표시한다. 이력에 남은 날짜가 그 조문이 실제로 시행된 단계라는 보장이 없으므로
     (실측: 분리 시행 179건 중 174건은 첫 단계, 5건은 마지막 단계 날짜) 그 날짜를 조문 시행일로 쓰지 않는다.

보안: OC 키는 환경변수에서만 읽고 출력하지 않는다. 이력 응답의 조문링크(OC 원문 포함)는 파서가 읽지
않는다. 출력 JSON에 키 문자열이 섞이면 저장하지 않고 실패한다.

v0.63.0 부칙 시행일 조항: 분리 시행 판본 조문 중 최근 변경이 제정·일부개정·전부개정인 것은 그 개정의
부칙 시행일 조항 원문을 함께 저장한다(법령별 `clauses["공포번호|공포일"]`). 서빙 판본의 eflaw 본문을
한 번 더 받아 `<부칙단위>`를 읽는다(서버 런타임 파서는 부칙을 읽지 않는다). 그 응답의 시행일자·법령ID가
서빙 판본과 다르거나 `<부칙단위>`가 없으면 그 법령은 실패로 센다. 생략 표시·①만 있음·끝맺음 이상·날짜
표현 부족·600자 초과·제어문자 등 형식이 의심스러운 조항은 넣지 않고 보고서에 사유를 적는다.

저장 게이트(하나라도 걸리면 기존 JSON·보고서를 건드리지 않고 종료 코드 2):
  - 대상 법령 전부 수록, 이력·부칙 조회 실패 0
  - 기존 스냅샷과 같은 판본(mst·efyd)인 법령은 조문 레코드가 같고 조항이 줄지 않음. 판본이 바뀌었거나
    조문이 달라졌거나 새 법령이면 --accept-diff 로 지정한 법령만 허용한다(보고서에 차이 기록)
  - --require-all-clauses 면 대상 조문 중 조항이 없는 것이 0건
  - 법령 id를 인자로 일부만 지정한 실행은 저장하지 않는다(부분 결과가 전체 파일을 덮지 않게)
저장은 임시 파일에 쓴 뒤 교체한다(쓰는 도중 끊겨도 기존 파일이 남는다). JSON → 보고서 순서이며, 보고서에
JSON 해시를 적는다(테스트가 짝을 대조).

사용:
  /Users/andykim/my_project/venv/bin/python scripts/extract_article_history.py            # law 전체
  /Users/andykim/my_project/venv/bin/python scripts/extract_article_history.py --dry-run  # 저장 없이 보고만
  ... --require-all-clauses                    # 대상 조문 모두 조항이 있어야 저장(릴리스 재생성)
  ... --accept-diff innovation_act,hakjin_act  # 판본 변경·조문 차이를 허용할 법령
종료 코드: 0 = 저장 완료(또는 dry-run 정상) / 2 = 게이트 미통과(저장 안 함, 사유 출력) / 3 = 키 없음·키 혼입 등 중단
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "src" / "korean_rnd_regs_mcp" / "article_history.json"
REPORT_PATH = ROOT / "scripts" / "article_history_extract_report.md"
SCHEMA_VERSION = 1
# 추출 규칙이 바뀌면 올린다 — JSON에 기록하고 테스트가 스크립트 값과 대조한다(낡은 데이터 배포 차단).
RULES_VERSION = 4  # v0.63.0: 부칙 시행일 조항(clauses) 추가
_MAX_STAGES = 6  # 런타임 로더(article_history._MAX_STAGES)와 같은 상한
_MAX_PROMULGATION_NO_LEN = 8
_KEEP_REASONS = frozenset({"제정", "조문변경", "본조신설", "전부개정"})
_NO_MARKER_REASONS = frozenset({"제정", "전부개정"})
_MARKER_DATE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})")
_DELETED_ARTICLE = re.compile(r"^제\s*\d+\s*조(?:의\s*\d+)?\s*삭제")
# 법령 종류는 API 문자열을 그대로 쓰되 이 목록 밖이면 추출 실패(시행령에 "법률"을 붙이는 오기 차단 — Redteam).
# 부령은 "과학기술정보통신부령"·"산업자원부령"처럼 부처명이 붙는다(2026-10-25 실측 11개 시행규칙).
LAW_KIND_PATTERN = re.compile(r"^(?:법률|대통령령|총리령|[가-힣]{1,12}부령)$")
_HISTORY_TIMEOUT = (5.0, 15.0)
_HISTORY_ATTEMPTS = 2
_HISTORY_MAX_ENTRIES = 200
_HISTORY_TEXT_MAX = 40
# v0.63.0 부칙 시행일 조항
_CLAUSE_AMENDMENTS = frozenset({"제정", "일부개정", "전부개정"})  # 허용 목록(타법개정·빈 값·낯선 값 제외)
_CLAUSE_MAX_CHARS = 600  # 런타임 로더(article_history._CLAUSE_MAX_CHARS)와 같은 상한
_BUCHIK_ATTEMPTS = 3
_BUCHIK_HEADER = re.compile(
    r"^\s*부칙(?:\([^)]*\))?\s*<\s*제?\s*(\d+)\s*호\s*,\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*>\s*$"
)
_ART1_SIHAENG = re.compile(r"^제1조\s*\([^)]*시행[^)]*\)")
# 다음 조의 시작 = 줄 첫머리의 "제N조(제목)". 제목 괄호가 없는 줄("제16조제2항의 개정규정: …")은 같은 조의 호다(Fable 재현).
_ART_LINE = re.compile(r"^\s*제\d+조(?:의\d+)?\s*\(")
_DATE_EXPR = re.compile(
    r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|공포한\s*날|공포\s*후\s*\d+\s*(?:년|개월|일)\s*이\s*경과한\s*날"
)
_CLAUSE_END = re.compile(r"(?:다\.|\d+\s*일)$")
_CLAUSE_BAD_CHARS = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def fetch_article_history(client, law_id: str, jo6: str) -> list[dict]:
    """조문별 변경 이력(lawService target=lsJoHstInf) 1건 조회 — 허용 필드만 읽는다.

    ★<조문링크>에는 OC 인증키 원문이 들어 있다(2026-10-24 실측 332/332) — 읽지 않는다.
    실패는 LawApiError(코드만 보고서에 남김). 서버 런타임은 이 함수를 쓰지 않는다(스냅샷만 읽음).
    """
    import xml.etree.ElementTree as ET
    from korean_rnd_regs_mcp.live_api import ERROR_NOT_FOUND, LawApiError, _parse_xml, _request_with_retry

    if not (law_id.isascii() and law_id.isdigit()):
        raise LawApiError(ERROR_NOT_FOUND, "law_id")
    resp = _request_with_retry(
        f"{client.base_url}/lawService.do",
        {"OC": client.api_key, "type": "XML", "target": "lsJoHstInf", "ID": law_id, "JO": jo6},
        max_retries=_HISTORY_ATTEMPTS, timeout=_HISTORY_TIMEOUT,
    )
    root = _parse_xml(resp)
    served = (root.findtext("법령ID") or "").strip()
    if served and served != law_id:
        raise LawApiError(ERROR_NOT_FOUND, "law_id_mismatch")

    def _t(el: ET.Element, path: str) -> str:
        return (el.findtext(path) or "").strip()[:_HISTORY_TEXT_MAX]

    laws = root.findall("law")
    if len(laws) > _HISTORY_MAX_ENTRIES:
        # 잘라 쓰면 더 최근 항목이 빠진 채 고를 수 있다 — 호출부가 그 조문을 제외하게 한다(diff 검토 Gemini·Grok).
        raise LawApiError(ERROR_NOT_FOUND, "too_many_entries")
    return [
        {
            "시행일자": _t(law, "법령정보/시행일자"),
            "공포일자": _t(law, "법령정보/공포일자"),
            "공포번호": _t(law, "법령정보/공포번호"),
            "제개정구분명": _t(law, "법령정보/제개정구분명"),
            "법령구분명": _t(law, "법령정보/법령구분명"),
            "법령일련번호": _t(law, "법령정보/법령일련번호"),
            "변경사유": _t(law, "조문정보/변경사유"),
            "조문번호": _t(law, "조문정보/조문번호"),
        }
        for law in laws
    ]


def _marker_promulgation(latest_history: str | None) -> str | None:
    """latest_history("본조신설 2026.5.26(공포)") → "20260526". 형식 이상이면 None."""
    if not latest_history:
        return None
    m = _MARKER_DATE.search(latest_history)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}{int(mo):02d}{int(d):02d}"


def _valid_date(raw: str) -> bool:
    if not (len(raw) == 8 and raw.isascii() and raw.isdigit()):
        return False
    try:
        time.strptime(raw, "%Y%m%d")
    except ValueError:
        return False
    return True


def _iso(raw: str) -> str:
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def select_entry(entries: list[dict], jo6: str, served_efyd: str) -> tuple[dict | None, str]:
    """이력 항목 목록 → (고른 항목, 사유). 고르지 못하면 (None, 제외 사유). 순수 함수(테스트 대상)."""
    if not entries:
        return None, "이력 없음"
    for e in entries:
        if (e.get("조문번호") or "") != jo6:
            return None, "조문번호 왕복 불일치"
    valid = [e for e in entries if _valid_date(e.get("시행일자", "")) and _valid_date(e.get("공포일자", ""))]
    if len(valid) != len(entries):
        return None, "날짜 형식 이상"
    current = [e for e in valid if e["시행일자"] <= served_efyd]
    if not current:
        return None, "서빙 시행일 이하 항목 없음"
    top = max(e["시행일자"] for e in current)
    tops = [e for e in current if e["시행일자"] == top]
    if len({e.get("공포번호", "") for e in tops}) > 1:
        return None, "같은 시행일에 공포번호 복수"
    keys = {(e["공포일자"], e.get("공포번호", ""), e.get("법령일련번호", ""), e.get("변경사유", ""), e.get("법령구분명", "")) for e in tops}
    if len(keys) > 1:
        return None, "같은 시행일에 항목 불일치"
    chosen = max(tops, key=lambda e: (e["공포일자"], e.get("법령일련번호", "")))
    if chosen.get("변경사유") not in _KEEP_REASONS:
        return None, f"변경사유 제외({chosen.get('변경사유') or '빈 값'})"
    no = chosen.get("공포번호", "")
    if not (no.isascii() and no.isdigit() and len(no) <= _MAX_PROMULGATION_NO_LEN):
        return None, "공포번호 형식 이상"
    if not LAW_KIND_PATTERN.match((chosen.get("법령구분명") or "").strip()):
        return None, "법령구분명 허용 밖"
    # 본문 표지는 공포일만 담는다 — 같은 날 다른 공포번호가 있으면 표지 대조로 판본을 가릴 수 없다(Redteam 2R).
    if any(e["공포일자"] == chosen["공포일자"] and e.get("공포번호") != chosen.get("공포번호") for e in valid):
        return None, "같은 공포일에 공포번호 복수"
    return chosen, "ok"


def marker_gate(chosen: dict, latest_history: str | None, content: str) -> str:
    """본문 표지 대조 — "ok" 또는 제외 사유. 순수 함수(테스트 대상)."""
    if _DELETED_ARTICLE.match((content or "").strip()) or (latest_history or "").startswith("삭제"):
        return "삭제된 조문"
    marker = _marker_promulgation(latest_history)
    if marker is None:
        if latest_history:
            return "표지 날짜 해석 불가"
        return "ok" if chosen["변경사유"] in _NO_MARKER_REASONS else "표지 없음(조문변경·본조신설)"
    return "ok" if marker == chosen["공포일자"] else "표지 공포일 불일치"


def stage_dates_for(rows: list[dict], version_mst: str) -> list[str]:
    """시행 단계 표에서 그 판본(법령일련번호)의 시행일 목록(정렬·중복 제거)."""
    dates = {(r.get("시행일자") or "").replace("-", "") for r in rows if r.get("법령일련번호") == version_mst}
    return sorted(d for d in dates if _valid_date(d))


def stage_gate(chosen: dict, entries: list[dict], rows: list[dict], served_efyd: str) -> str:
    """시행 단계 표 대조 — "ok" 또는 제외 사유. 순수 함수(테스트 대상).

    ① 고른 항목의 판본(법령일련번호)이 시행 단계 표에 없거나 그 시행일이 표에 없으면 단일·분리 시행을
       가릴 수 없으므로 뺀다("단일 시행 확인"과 "단계 정보 미확인"을 구분 — 구현 diff 검토 Codex MAJOR).
    ② 서빙 시행일보다 뒤로 기록된 항목의 판본이 이미 일부 단계 시행됐으면 뺀다. 이력은 분리 시행 판본을
       한 단계 날짜로만 남기는데 그것이 마지막 단계일 수 있어(2026-10-25 실측: 법률 제21421호 06-11·09-11 →
       이력 09-11), 서빙 시행일이 단계 사이면 이미 시행된 변경이 미래 항목으로 보여 더 오래된 판본을 고르게
       된다(Redteam 2라운드).
       그 판본이 표에 없어도 귀속을 확인할 수 없으므로 뺀다.
    """
    dates = stage_dates_for(rows, chosen.get("법령일련번호", ""))
    if not dates:
        return "단계 표 미확인"
    if len(dates) > _MAX_STAGES:
        return "시행 단계 상한 초과"
    if chosen.get("시행일자", "") not in dates:
        return "단계 표 불일치"
    for e in entries:
        if e.get("시행일자", "") > served_efyd:
            later = stage_dates_for(rows, e.get("법령일련번호", ""))
            if not later:
                return "단계 표 미확인"
            if any(d <= served_efyd for d in later):
                return "분리 시행 단계 귀속 불명"
    return "ok"


def build_record(chosen: dict, stage_dates: list[str]) -> dict:
    rec = {
        "law_kind": chosen["법령구분명"].strip(),
        "promulgation_no": chosen["공포번호"],
        "promulgation_date": _iso(chosen["공포일자"]),
        "version_effective_date": _iso(chosen["시행일자"]),
        "amendment_kind": (chosen.get("제개정구분명") or "").strip(),
        "change_reason": chosen["변경사유"],
    }
    if len(stage_dates) > 1:
        rec["staged_dates"] = [_iso(d) for d in stage_dates]
    return rec


# === v0.63.0 부칙 시행일 조항 ===

def fetch_buchik_units(client, mst: str, efyd8: str, law_id: str) -> list[dict]:
    """서빙 판본의 eflaw 본문에서 <부칙단위> 목록 [{"no","date","text"}]. 판본이 다르거나 부칙이 없으면 LawApiError.

    응답의 기본정보에는 법령일련번호가 없어 시행일자·법령ID로 판본을 대조한다(2026-10-28 실측).
    """
    from korean_rnd_regs_mcp.live_api import ERROR_NOT_FOUND, LawApiError, _parse_xml, _request_with_retry

    resp = _request_with_retry(
        f"{client.base_url}/lawService.do",
        {"OC": client.api_key, "target": "eflaw", "type": "XML", "MST": mst, "efYd": efyd8},
        max_retries=_BUCHIK_ATTEMPTS, timeout=(5.0, 30.0),
    )
    root = _parse_xml(resp)
    got_efyd = re.sub(r"\D", "", root.findtext("기본정보/시행일자") or "")
    got_id = (root.findtext("기본정보/법령ID") or "").strip()
    if got_efyd != re.sub(r"\D", "", efyd8) or got_id != law_id:
        raise LawApiError(ERROR_NOT_FOUND, "buchik_version_mismatch")
    units = []
    for u in root.findall(".//부칙단위"):
        el = u.find("부칙내용")
        units.append({
            "no": (u.findtext("부칙공포번호") or "").strip(),
            "date": re.sub(r"\D", "", u.findtext("부칙공포일자") or ""),
            "text": "".join(el.itertext()) if el is not None else "",
        })
    if not units:
        raise LawApiError(ERROR_NOT_FOUND, "buchik_absent")
    return units


def _num_eq(a: str, b: str) -> bool:
    """공포번호 비교 — 앞 0 차이는 같은 번호(레코드 "00221" ↔ 부칙 "221")."""
    return a.isascii() and a.isdigit() and b.isascii() and b.isdigit() and int(a) == int(b)


def extract_clause(text: str, promulgation_no: str, promulgation_date: str, n_stages: int,
                   api_key: str = "") -> tuple[str | None, str]:
    """부칙 원문 1건 → (시행일 조항 원문, "ok") 또는 (None, 제외 사유). 순수 함수(테스트 대상).

    promulgation_date는 ISO(YYYY-MM-DD). 첫 줄 머리말의 번호·날짜가 레코드와 같아야 하고, 본문이
    `제1조(…시행…)`로 시작하면 줄 첫머리의 다음 `제N조` 앞에서 자른다. 조번호 줄이 없는 한 문장 부칙은
    본문 전체를 쓴다. 그 밖의 형태는 넣지 않는다.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    m = _BUCHIK_HEADER.match(lines[0]) if lines else None
    if not m:
        return None, "머리말 형식 이상"
    y, mo, d = m.group(2), int(m.group(3)), int(m.group(4))
    if not _num_eq(m.group(1), promulgation_no) or f"{y}-{mo:02d}-{d:02d}" != promulgation_date:
        return None, "머리말 번호·날짜 불일치"
    body = [ln.rstrip() for ln in lines[1:]]
    while body and not body[0].strip():
        body.pop(0)
    if not body:
        return None, "본문 없음"
    if _ART1_SIHAENG.match(body[0].strip()):
        cut = len(body)
        for i in range(1, len(body)):
            if _ART_LINE.match(body[i]):
                cut = i
                break
        clause = "\n".join(body[:cut]).strip()
    elif not any(_ART_LINE.match(ln) for ln in body) and "시행" in "\n".join(body):
        clause = "\n".join(body).strip()
    else:
        return None, "시행일 조항 형태 아님"
    if "생략" in clause:
        return None, "생략 표시"
    if ("①" in clause) != ("②" in clause):
        return None, "①·② 짝 없음"
    if not _CLAUSE_END.search(clause):
        return None, "끝맺음 이상"
    if len(_DATE_EXPR.findall(clause)) < n_stages:
        return None, "날짜 표현 부족"
    if len(clause) > _CLAUSE_MAX_CHARS:
        return None, "600자 초과"
    if _CLAUSE_BAD_CHARS.search(clause):
        return None, "제어문자"
    if "OC=" in clause or "http" in clause.lower() or (api_key and api_key in clause):
        return None, "키·링크 문자열"
    return clause, "ok"


def clause_targets(articles: dict) -> dict[str, dict]:
    """조항을 실어야 할 레코드 {조문 키: 레코드} — 분리 시행 + 허용 개정."""
    return {uid: r for uid, r in articles.items()
            if r.get("staged_dates") and r.get("amendment_kind") in _CLAUSE_AMENDMENTS}


def build_clauses(articles: dict, units: list[dict], api_key: str = "") -> tuple[dict, dict[str, str]]:
    """법령 1개의 조항 dict와 조항을 못 붙인 대상 {조문 키: 사유}. 키 = 레코드의 "공포번호|공포일" 그대로."""
    clauses: dict = {}
    missing: dict[str, str] = {}
    cache: dict[str, tuple[str | None, str]] = {}
    targets = clause_targets(articles)
    stages_by_key: dict[str, set] = {}
    for r in targets.values():
        stages_by_key.setdefault(f"{r['promulgation_no']}|{r['promulgation_date']}", set()).add(tuple(r["staged_dates"]))
    for key, stages in stages_by_key.items():
        if len(stages) > 1:  # 같은 개정인데 단계 목록이 다르면 어느 쪽 날짜 수로 검사할지 정할 수 없다
            cache[key] = (None, "단계 목록 불일치")
    for uid, r in sorted(targets.items()):
        key = f"{r['promulgation_no']}|{r['promulgation_date']}"
        if key not in cache:
            date8 = r["promulgation_date"].replace("-", "")
            hits = [u for u in units if _num_eq(u["no"], r["promulgation_no"]) and u["date"] == date8]
            if len(hits) != 1:
                cache[key] = (None, "부칙 0건" if not hits else "부칙 복수")
            else:
                cache[key] = extract_clause(hits[0]["text"], r["promulgation_no"], r["promulgation_date"],
                                            len(r["staged_dates"]), api_key)
        text, why = cache[key]
        if text is None:
            missing[uid] = why
        else:
            clauses[key] = {"text": text}
    return clauses, missing


def diff_against_existing(old_laws: dict, new_laws: dict) -> dict[str, str]:
    """저장 게이트 G2 — 기존 스냅샷과 다른 법령 {rule_set_id: 사유}. 같은 판본이면 조문 레코드가 같고 조항이 줄지 않아야 한다."""
    out: dict[str, str] = {}
    for rid, new in new_laws.items():
        old = old_laws.get(rid)
        if not isinstance(old, dict):
            out[rid] = "새 법령"
            continue
        if (old.get("mst"), old.get("efyd")) != (new.get("mst"), new.get("efyd")):
            out[rid] = f"판본 변경 {old.get('mst')}·{old.get('efyd')} → {new.get('mst')}·{new.get('efyd')}"
            continue
        if old.get("articles") != new.get("articles"):
            o, n = old.get("articles") or {}, new.get("articles") or {}
            changed = sum(1 for k in set(o) | set(n) if o.get(k) != n.get(k))
            out[rid] = f"같은 판본에서 조문 레코드 {changed}건 차이"
            continue
        oc, nc = old.get("clauses") or {}, new.get("clauses") or {}
        lost = set(oc) - set(nc)
        if lost:
            out[rid] = f"조항 {len(lost)}건 감소"
            continue
        changed_text = [k for k in set(oc) & set(nc) if oc[k] != nc[k]]
        if changed_text:
            out[rid] = f"조항 {len(changed_text)}건 원문 변경"
    for rid in old_laws:
        if rid not in new_laws:
            out[rid] = "법령 빠짐"
    return out


def _write_pair(json_path: Path, json_text: str, report_path: Path, report_text: str) -> None:
    """JSON → 보고서 순으로 교체한다. 보고서 교체가 실패하면 JSON을 이전 내용으로 되돌리고 예외를 다시 던진다."""
    old_json = json_path.read_bytes() if json_path.exists() else None
    _write_atomic(json_path, json_text)
    try:
        _write_atomic(report_path, report_text)
    except BaseException:
        if old_json is None:
            json_path.unlink(missing_ok=True)
        else:
            _write_atomic(json_path, old_json.decode("utf-8"))
        raise


def _write_atomic(path: Path, text: str) -> None:
    """같은 폴더의 임시 파일에 쓰고 fsync 뒤 교체한다. 실패하면 임시 파일을 지우고 예외를 다시 던진다."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--require-all-clauses", action="store_true",
                    help="대상 조문 중 부칙 시행일 조항이 없는 것이 하나라도 있으면 저장하지 않음")
    ap.add_argument("--accept-diff", default="",
                    help="기존 스냅샷과의 차이(판본 변경·조문 차이·새 법령)를 허용할 rule_set_id 목록(쉼표 구분)")
    args = ap.parse_args(argv)
    accept = {s.strip() for s in args.accept_diff.split(",") if s.strip()}
    save = not args.dry_run and not args.ids  # 일부 법령만 지정한 실행은 저장하지 않는다

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    from korean_rnd_regs_mcp.live_api import LawApiClient, LawApiError
    from korean_rnd_regs_mcp.main import _article_amendment_history, _article_unit_id
    from korean_rnd_regs_mcp.manifest import load_manifest
    from audit_law_stage_diff import Collector

    client = LawApiClient()
    if not client.api_key:
        print("LAW_API_KEY 없음 — 중단")
        return 3
    col = Collector(client, None)
    targets = [r for r in load_manifest() if r.api_target.value == "law" and (not args.ids or r.id in args.ids)]
    laws: dict = {}
    report: list[str] = []
    failed = 0
    excluded_total: dict[str, int] = {}
    clause_missing: dict[str, str] = {}  # "rule_set_id|JO…" → 사유
    clause_targets_n = 0
    for rs in targets:
        try:
            resolved = client.resolve_latest_doc_id(rs.title, "law", rs.api_doc_id, rs.ministry)
            detail, stage = client.get_law_detail_staged(resolved.doc_id, resolved.effective_date, rs.title)
            if stage != "eflaw":
                failed += 1
                report.append(f"| {rs.id} | 미수록 | 본문 단계 {stage} |")
                continue
            efyd = (detail.get("시행일자") or "").replace("-", "")
            law_id = (detail.get("법령ID") or "").strip()
            rows = col.stage_rows(rs.title, rs.ministry)
            if not rows:
                failed += 1
                report.append(f"| {rs.id} | 미수록 | 시행 단계 표 미확보 |")
                continue
            arts: dict = {}
            excl: dict[str, int] = {}

            def _one(art):
                uid = _article_unit_id(art)
                if uid is None:
                    return None, None, "JO 인코딩 불가"
                digits = uid[2:]
                jo6 = digits if len(digits) == 6 else digits + "00"
                try:
                    entries = fetch_article_history(client, law_id, jo6)
                except LawApiError as e:
                    return uid, None, f"이력 조회 실패({e.code})"
                chosen, why = select_entry(entries, jo6, efyd)
                if chosen is not None:
                    why = stage_gate(chosen, entries, rows, efyd)
                if why == "ok":
                    why = marker_gate(chosen, _article_amendment_history(art), art.get("조문내용", ""))
                if why != "ok":
                    return uid, None, why
                return uid, build_record(chosen, stage_dates_for(rows, chosen.get("법령일련번호", ""))), "ok"

            with ThreadPoolExecutor(max_workers=6) as ex:
                results = list(ex.map(_one, detail.get("articles", [])))
            # 같은 JO가 본문에 두 번 나오면 서버가 서빙하는 쪽(첫 번째)과 검증한 쪽이 다를 수 있다 — 제외.
            seen_uid: dict[str, int] = {}
            for uid, _rec, _why in results:
                if uid is not None:
                    seen_uid[uid] = seen_uid.get(uid, 0) + 1
            dup = {u for u, n in seen_uid.items() if n > 1}
            results = [(u, None, "조문 번호 중복") if u in dup else (u, r, w) for u, r, w in results]
            for uid, rec, why in results:
                if rec is None:
                    excl[why] = excl.get(why, 0) + 1
                else:
                    arts[uid] = rec
            entry = {"mst": resolved.doc_id, "efyd": _iso(efyd), "law_id": law_id, "articles": arts}
            note = ""
            if clause_targets(arts):
                units = fetch_buchik_units(client, resolved.doc_id, efyd, law_id)
                clauses, missing = build_clauses(arts, units, client.api_key)
                if clauses:
                    entry["clauses"] = clauses
                clause_targets_n += len(clause_targets(arts))
                for uid, why in missing.items():
                    clause_missing[f"{rs.id}|{uid}"] = why
                note = f" · 부칙 조항 {len(clauses)}건(대상 {len(clause_targets(arts))}, 미수록 {len(missing)})"
            laws[rs.id] = entry
            staged = sum(1 for a in arts.values() if "staged_dates" in a)
            n = len(detail.get("articles", []))
            report.append(f"| {rs.id} | {len(arts)}/{n} | 분리 시행 {staged} · 제외 {dict(sorted(excl.items()))}{note} |")
            for k, v in excl.items():
                excluded_total[k] = excluded_total.get(k, 0) + v
            print(f"{rs.id}: {len(arts)}/{n} staged={staged}", flush=True)
        except LawApiError as e:
            failed += 1
            report.append(f"| {rs.id} | 미수록 | 오류 {e.code} |")
        except Exception as e:  # noqa: BLE001 — 한 법령 실패가 전체를 막지 않게
            failed += 1
            report.append(f"| {rs.id} | 미수록 | 예외 {type(e).__name__} |")

    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    payload = {
        "schema": SCHEMA_VERSION,
        "rules_version": RULES_VERSION,
        "generated_at": now,
        "source": "국가법령정보 공동활용 OpenAPI lawService target=lsJoHstInf(조문별 변경 이력)",
        "laws": laws,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    if client.api_key in text or "OC=" in text:
        print("출력에 키 혼입 — 저장 중단")
        return 3
    json_text = text + "\n"
    total = sum(len(v["articles"]) for v in laws.values())
    n_clauses = sum(len(v.get("clauses") or {}) for v in laws.values())
    fetch_failures = sum(v for k, v in excluded_total.items() if k.startswith("이력 조회 실패"))

    # 저장 게이트 — 하나라도 걸리면 기존 파일을 건드리지 않는다.
    blocks: list[str] = []
    if failed or len(laws) != len(targets):
        blocks.append(f"미수록 법령 {failed}건(수록 {len(laws)}/{len(targets)})")
    if fetch_failures:
        blocks.append(f"이력 조회 실패 {fetch_failures}건")
    try:
        old_raw = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        old_laws = old_raw.get("laws") if isinstance(old_raw, dict) else None
        if not isinstance(old_laws, dict):
            raise ValueError("laws")
    except FileNotFoundError:
        old_laws = {}  # 첫 생성
    except (OSError, ValueError):
        old_laws = {}
        blocks.append("기존 스냅샷을 읽지 못해 비교할 수 없음(파일 확인 필요)")
    diffs = diff_against_existing(old_laws, laws) if old_laws and not args.ids else {}
    unaccepted = {rid: why for rid, why in diffs.items() if rid not in accept}
    if unaccepted:
        blocks.append("기존 스냅샷과 차이(--accept-diff 필요): "
                      + "; ".join(f"{rid} {why}" for rid, why in sorted(unaccepted.items())))
    if args.require_all_clauses and clause_missing:
        blocks.append(f"부칙 시행일 조항 미수록 {len(clause_missing)}건")

    lines = [
        "# 조문별 변경 이력 스냅샷 생성 보고",
        "",
        f"- 생성: {now} · 법령 {len(laws)}/{len(targets)} 수록 · 조문 {total}건 · 미수록 법령 {failed}",
        f"- 제외 사유 합계: {dict(sorted(excluded_total.items()))}",
        f"- 부칙 시행일 조항: 대상 {clause_targets_n}건 · 수록 조항 {n_clauses}개 · 조항 없는 대상 {len(clause_missing)}건",
        f"- 기존 스냅샷과 차이: {dict(sorted(diffs.items())) or '없음'}",
        f"- JSON sha256: {hashlib.sha256(json_text.encode('utf-8')).hexdigest()}",
        "",
        "| rule_set_id | 수록/전체 조문 | 비고 |",
        "|---|---|---|",
        *report,
        "",
        "## 조항 없는 대상",
        "",
        *([f"- {k}: {v}" for k, v in sorted(clause_missing.items())] or ["- 없음"]),
        "",
        "## 수록한 부칙 시행일 조항(원문 대조용)",
        "",
    ]
    for rid in sorted(laws):
        for key, val in sorted((laws[rid].get("clauses") or {}).items()):
            lines.append(f"### {rid} · {key}")
            lines.append("")
            lines.extend(f"> {ln}" if ln else ">" for ln in val["text"].split("\n"))
            lines.append("")
    report_text = "\n".join(lines)
    if client.api_key in report_text or "OC=" in report_text:
        print("보고서에 키 혼입 — 저장 중단")
        return 3

    print("\n".join(lines[:7]))
    if blocks:
        for row in report:
            if "미수록" in row.split("|")[2]:
                print(row)
        for k, v in sorted(clause_missing.items()):
            print(f"조항 없는 대상: {k}: {v}")
        print("저장 안 함 — " + " / ".join(blocks))
        return 2
    if save:
        try:
            _write_pair(OUT_PATH, json_text, REPORT_PATH, report_text)
        except OSError as e:
            print(f"저장 실패({type(e).__name__}) — 기존 파일 유지")
            return 2
    elif not args.dry_run:
        print("일부 법령만 지정한 실행이라 저장하지 않음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
