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
  - 기존 스냅샷과 같은 판본(mst·efyd)인 법령은 조문 단위 기존 필드가 바이트 동일해야 한다 — 다르면 어떤
    플래그로도 저장하지 않는다(v0.66.0 Redteam diff Codex MAJOR). 같은 판본에서 조항이 줄거나 원문이 바뀐 경우,
    판본이 바뀐 법령·새 법령은 --accept-diff 로 지정한 법령만 허용한다(보고서에 차이 기록)
  - --require-all-clauses 면 대상 조문 중 조항이 없는 것이 0건
  - 법령 id를 인자로 일부만 지정한 실행은 저장하지 않는다(부분 결과가 전체 파일을 덮지 않게)
저장은 임시 파일에 쓴 뒤 교체한다(쓰는 도중 끊겨도 기존 파일이 남는다). JSON → 보고서 순서이며, 보고서에
JSON 해시를 적는다(테스트가 짝을 대조).

v0.66.0 항별 개정 표지: 항번호가 있는 항의 `항내용` 끝 꺾쇠 표지(서버 main의 정규식·라벨 규칙)에서 표지 안
가장 늦은 날짜(공포일)를 같은 조문 이력의 공포일자 항목(공포번호 1개)과 대응시켜 공포번호별 그룹을 만든다.
대응 실패(공포번호 0·복수, 단계 표 없음, 호·목 표지가 더 늦음, 한 항 다중 표지 유형 다름, 빈 라벨)면 그 조문은
싣지 않는다. 그룹 2개 이상이거나 조문 단위 레코드가 없는 조문만 싣는다(조문 레코드에 `paragraphs`, 레코드가
없으면 `paragraphs`만 가진 레코드). 분리 시행 그룹은 부칙 시행일 조항도 찾되, 못 찾아도 저장은 막지 않는다.
저장 게이트: 같은 판본 법령의 조문 단위 기존 필드는 바이트 동일해야 하고(다르면 무조건 중단), 항별 데이터의 추가·변경은
--accept-paragraphs 로만 허용한다. 대상과 대응 실패 집합의 교집합, 항별 블록으로 인한 크기 단계 변화가 있으면
저장하지 않는다. 보고서에 결박 수치(계획서 5-3)를 적는다.

사용:
  /Users/andykim/my_project/venv/bin/python scripts/extract_article_history.py            # law 전체
  /Users/andykim/my_project/venv/bin/python scripts/extract_article_history.py --dry-run  # 저장 없이 보고만
  ... --require-all-clauses                    # 대상 조문 모두 조항이 있어야 저장(릴리스 재생성)
  ... --accept-diff innovation_act,hakjin_act  # 판본 변경·조문 차이를 허용할 법령
  ... --accept-paragraphs                      # 항별 데이터 추가·변경 허용(v0.66.0)
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
RULES_VERSION = 5  # v0.63.0: 부칙 시행일 조항(clauses) · v0.66.0: 항별 개정 표지(paragraphs)
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


# === v0.66.0 항별 개정 표지(항 본문 끝 꺾쇠 표지) ===
# 표지 해석은 서버(main)의 정규식·라벨 규칙을 그대로 쓴다(측정용 별도 정규식 금지 — 계획서 5-3).
_PARA_LABELS = frozenset({"개정", "신설", "삭제"})
_MAX_PARA_NO = 99
_AMENDMENT_KIND_PATTERN = re.compile(r"[가-힣]{0,10}")  # 런타임 로더(article_history._AMENDMENT_KIND)와 같은 형식


def para_number(raw: str) -> int | None:
    """항번호("①"·"⑳"·"㉑"·"㊱" 또는 숫자) → 정수. 해석 불가면 None."""
    s = (raw or "").strip()
    if len(s) == 1:
        c = ord(s)
        if 0x2460 <= c <= 0x2473:
            return c - 0x2460 + 1
        if 0x3251 <= c <= 0x325F:
            return c - 0x3251 + 21
        if 0x32B1 <= c <= 0x32BF:
            return c - 0x32B1 + 36
    s = s.rstrip(".")
    if s.isascii() and s.isdigit() and 1 <= len(s) <= 2 and int(s) >= 1:
        return int(s)
    return None


def scan_markers(text: str) -> list[dict]:
    """본문 조각의 꺾쇠 표지(날짜 있는 것만) → [{"label", "dates": [(y, m, d), ...]}]. 순수 함수."""
    from korean_rnd_regs_mcp.main import (_CONTENT_HISTORY_MARKER, _HISTORY_DATE_PATTERN,
                                          _content_marker_label, _parse_history_date)
    out = []
    for m in _CONTENT_HISTORY_MARKER.finditer(text or ""):
        del_prefix, inner = m.group(1), m.group(2)
        raw_dates = _HISTORY_DATE_PATTERN.findall(inner)
        if not raw_dates:
            continue
        dates = [d for d in (_parse_history_date(x) for x in raw_dates) if d is not None]
        if not dates:
            continue
        out.append({"label": _content_marker_label(del_prefix, inner), "dates": dates})
    return out


def _d8(dt: tuple) -> str:
    return f"{dt[0]:04d}{dt[1]:02d}{dt[2]:02d}"


def paragraph_markers(art: dict) -> tuple[list[dict] | None, str, dict]:
    """조문 1개 → (항별 표지 목록, "ok" 또는 실패 사유, 통계). 순수 함수(테스트 대상).

    항 표지 = 항번호가 있는 항의 `항내용`에 있는 꺾쇠 표지. 날짜는 표지 안 가장 늦은 날짜(달력 비교).
    조문내용 제목 줄·호·목 표지는 쓰지 않되, 항 아래 호·목(조문내용에서 그 항 뒤 ~ 다음 항 앞)에 항 표지보다
    늦은 날짜가 있으면 그 조문은 실패로 둔다(항 표지가 항 전체의 최근 변경을 말하지 않음).
    목록 원소: {"no": int, "label": str, "date8": 가장 늦은 날짜, "first8": 첫 날짜, "n_dates": 날짜 수}.
    """
    stats = {"self_markers": 0, "multi_date": 0, "multi_marker_paras": 0, "sub_only_paras": 0, "sub_later_paras": 0,
             "sub_only_wrappers": 0, "relabel_new_to_amend": 0, "marker_dates": []}
    structured = art.get("structured")
    paras = [p for p in ((structured or {}).get("paragraphs") or []) if isinstance(p, dict)] \
        if isinstance(structured, dict) else []
    if not paras:
        return [], "ok", stats
    content = art.get("조문내용") or ""
    # 조문내용 = 제목 줄 + 항내용 + 호·목 원문을 순서대로 이은 것(live_api._build_article_content) — 항 위치를 차례로 찾는다.
    positions: list[tuple[int, int] | None] = []
    cursor = 0
    for p in paras:
        src = p.get("source_text") or ""
        if not src:
            positions.append(None)
            continue
        at = content.find(src, cursor)
        if at < 0:
            if any(scan_markers(q.get("source_text") or "") for q in paras):
                return None, "항 본문 위치 불일치", stats
            return [], "ok", stats
        positions.append((at, at + len(src)))
        cursor = at + len(src)
    starts = [pos[0] for pos in positions if pos is not None]
    out: list[dict] = []
    failure = ""
    seen_no: set[int] = set()
    for p, pos in zip(paras, positions):
        if pos is None:
            # 번호·본문 없는 항(호만 묶는 틀) — 쓰지 않되 호 표지 수만 센다(보고서용).
            if any(scan_markers((s or {}).get("source_text") or "") for s in p.get("subparagraphs") or []
                   if isinstance(s, dict)):
                stats["sub_only_wrappers"] += 1
            continue
        nxt = min((s for s in starts if s > pos[0]), default=len(content))
        sub = content[pos[1]:nxt]
        own = scan_markers(p.get("source_text") or "")
        sub_m = scan_markers(sub)
        if not own:
            if sub_m:
                stats["sub_only_paras"] += 1
            continue
        stats["self_markers"] += len(own)
        stats["multi_date"] += sum(1 for m in own if len(m["dates"]) > 1)
        latest = max(d for m in own for d in m["dates"])
        first = own[0]["dates"][0]
        n_dates = sum(len(m["dates"]) for m in own)
        stats["marker_dates"].append((_d8(latest), _d8(first)))
        if len(own) > 1:
            stats["multi_marker_paras"] += 1
            if len({m["label"] for m in own}) > 1:
                failure = failure or "한 항 다중 표지 유형 다름"
                continue
        label = own[0]["label"]
        if label == "신설" and n_dates > 1:
            # 표지 안 가장 늦은 날짜는 신설 뒤의 개정이다(예 `<신설 2021.1.19, 2026.5.19>`의 2026.5.19) — 그 날짜와
            # 대응한 판본은 이 항을 만든 판본이 아니므로 '개정'으로 적는다(Redteam diff Fable MAJOR). 서버의
            # latest_history 라벨 규칙(main._content_marker_label)은 별도 계약이라 바꾸지 않는다.
            label = "개정"
            stats["relabel_new_to_amend"] += 1
        if sub_m and max(d for m in sub_m for d in m["dates"]) > latest:
            stats["sub_later_paras"] += 1
            failure = failure or "호·목 표지가 항 표지보다 늦음"
            continue
        no = para_number(p.get("number") or "")
        if no is None or no > _MAX_PARA_NO:
            failure = failure or "항 번호 해석 불가"
            continue
        if no in seen_no:
            failure = failure or "항 번호 중복"
            continue
        seen_no.add(no)
        if label not in _PARA_LABELS:
            failure = failure or "빈 라벨"
            continue
        out.append({"no": no, "label": label, "date8": _d8(latest), "first8": _d8(first), "n_dates": n_dates})
    if failure:
        return None, failure, stats
    return out, "ok", stats


def match_paragraphs(markers: list[dict], entries: list[dict], jo6: str, rows: list[dict]) -> tuple[list[dict] | None, str]:
    """항 표지 → 공포번호별 그룹 목록(또는 None, 실패 사유). 순수 함수(테스트 대상).

    표지 날짜(공포일)와 같은 공포일자의 이력 항목이 공포번호 1개로 정해져야 하고, 그 판본(법령일련번호)이
    시행 단계 표에 있어야 한다. 하나라도 어긋나면 그 조문은 항별 블록을 싣지 않는다(안전 쪽 실패).
    그룹: {"promulgation_no","promulgation_date","law_kind","amendment_kind","version_effective_date",
           ["staged_dates"], "items": [[항번호 문자열, 라벨], ...]} — 항번호 순.
    """
    if not markers:
        return [], "ok"
    if not entries:
        return None, "이력 없음"
    if any((e.get("조문번호") or "") != jo6 for e in entries):
        return None, "조문번호 왕복 불일치"
    if any(not (_valid_date(e.get("시행일자", "")) and _valid_date(e.get("공포일자", ""))) for e in entries):
        return None, "날짜 형식 이상"
    groups: dict[str, dict] = {}
    for mk in markers:
        hits = [e for e in entries if e["공포일자"] == mk["date8"]]
        nos = {e.get("공포번호", "") for e in hits}
        if not hits:
            return None, "이력에 없음"
        if len(nos) > 1:
            return None, "공포번호 복수"
        keys = {(e.get("법령일련번호", ""), e["시행일자"], (e.get("법령구분명") or "").strip(),
                 (e.get("제개정구분명") or "").strip()) for e in hits}
        if len(keys) > 1:
            return None, "같은 공포번호에 항목 불일치"
        e = hits[0]
        no = e.get("공포번호", "")
        if not (no.isascii() and no.isdigit() and len(no) <= _MAX_PROMULGATION_NO_LEN):
            return None, "공포번호 형식 이상"
        kind = (e.get("법령구분명") or "").strip()
        if not LAW_KIND_PATTERN.fullmatch(kind):
            return None, "법령구분명 허용 밖"
        amendment_kind = (e.get("제개정구분명") or "").strip()
        if not _AMENDMENT_KIND_PATTERN.fullmatch(amendment_kind):
            return None, "제개정구분명 형식 밖"  # 런타임 로더와 같은 형식 — 잘라 저장하지 않는다
        dates = stage_dates_for(rows, e.get("법령일련번호", ""))
        if not dates:
            return None, "단계 표 없음"
        if len(dates) > _MAX_STAGES:
            return None, "시행 단계 상한 초과"
        if e["시행일자"] not in dates:
            return None, "단계 표 불일치"
        g = groups.get(no)
        if g is None:
            g = {
                "promulgation_no": no,
                "promulgation_date": _iso(e["공포일자"]),
                "law_kind": kind,
                "amendment_kind": amendment_kind,
                "version_effective_date": _iso(e["시행일자"]),
                "items": [],
            }
            if len(dates) > 1:
                g["staged_dates"] = [_iso(d) for d in dates]
            groups[no] = g
        g["items"].append([str(mk["no"]), mk["label"]])
    out = []
    for g in groups.values():
        g["items"].sort(key=lambda it: int(it[0]))
        out.append(g)
    out.sort(key=lambda g: int(g["items"][0][0]))
    return out, "ok"


def paragraph_decision(groups: list[dict], record: dict | None) -> str:
    """그룹 목록과 조문 단위 레코드 → "attach"·"none"·"single_same"·"single_differs". 순수 함수(테스트 대상).

    붙이는 조건(계획서 5-1): 그룹 2개 이상이거나 조문 단위 레코드가 없는 조문. 그룹 1개면 레코드와 같든
    다르든 붙이지 않는다(같으면 중복, 다르면 2건뿐이라 단순성 우선).
    """
    if not groups:
        return "none"
    if record is None or len(groups) >= 2:
        return "attach"
    return "single_same" if _num_eq(groups[0]["promulgation_no"], record["promulgation_no"]) else "single_differs"


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


def paragraph_clause_targets(articles: dict) -> dict[str, dict]:
    """v0.66.0 조항을 실어야 할 항별 그룹 {"조문 키|공포번호": 그룹} — 분리 시행 + 허용 개정(조문 단위와 같은 규칙)."""
    out = {}
    for uid, r in articles.items():
        for g in r.get("paragraphs") or []:
            if g.get("staged_dates") and g.get("amendment_kind") in _CLAUSE_AMENDMENTS:
                out[f"{uid}|{g['promulgation_no']}"] = g
    return out


def build_paragraph_clauses(articles: dict, units: list[dict], clauses: dict,
                            api_key: str = "") -> tuple[dict, dict[str, str]]:
    """항별 분리 시행 그룹의 부칙 시행일 조항 — (새로 더할 조항, 못 붙인 그룹 {"조문 키|공포번호": 사유}).

    키는 조문 단위와 같은 "공포번호|공포일". 조문 단위가 이미 실은 조항은 그대로 쓴다. 같은 개정인데 단계 목록이
    조문 단위·다른 그룹과 다르면 넣지 않는다. 못 붙여도 저장은 막지 않는다(런타임이 목록 문장으로 낸다).
    """
    added: dict = {}
    missing: dict[str, str] = {}
    targets = paragraph_clause_targets(articles)
    stages_by_key: dict[str, set] = {}
    for r in clause_targets(articles).values():
        stages_by_key.setdefault(f"{r['promulgation_no']}|{r['promulgation_date']}", set()).add(tuple(r["staged_dates"]))
    for g in targets.values():
        stages_by_key.setdefault(f"{g['promulgation_no']}|{g['promulgation_date']}", set()).add(tuple(g["staged_dates"]))
    cache: dict[str, tuple[str | None, str]] = {}
    for tid, g in sorted(targets.items()):
        key = f"{g['promulgation_no']}|{g['promulgation_date']}"
        if key not in cache:
            if len(stages_by_key.get(key, set())) > 1:
                cache[key] = (None, "단계 목록 불일치")
            elif key in clauses:
                cache[key] = (clauses[key]["text"], "ok")
            else:
                date8 = g["promulgation_date"].replace("-", "")
                hits = [u for u in units if _num_eq(u["no"], g["promulgation_no"]) and u["date"] == date8]
                if len(hits) != 1:
                    cache[key] = (None, "부칙 0건" if not hits else "부칙 복수")
                else:
                    cache[key] = extract_clause(hits[0]["text"], g["promulgation_no"], g["promulgation_date"],
                                                len(g["staged_dates"]), api_key)
        text, why = cache[key]
        if text is None:
            missing[tid] = why
        elif key not in clauses:
            added[key] = {"text": text}
    return added, missing


def _legacy_view(articles: dict) -> dict:
    """조문 단위 레코드의 기존 필드만(항별 `paragraphs` 제외, 항별 전용 레코드 제외) — 저장 게이트 비교용."""
    out = {}
    for uid, r in (articles or {}).items():
        if isinstance(r, dict) and "promulgation_no" in r:
            out[uid] = {k: v for k, v in r.items() if k != "paragraphs"}
        elif not (isinstance(r, dict) and set(r) == {"paragraphs"}):
            out[uid] = r  # 형식 밖 레코드는 그대로 비교(차이로 잡힘)
    return out


def _paragraph_view(articles: dict) -> dict:
    return {uid: r.get("paragraphs") for uid, r in (articles or {}).items()
            if isinstance(r, dict) and r.get("paragraphs") is not None}


def legacy_bytes_equal(old: dict, new: dict) -> bool:
    """두 조문 단위 레코드 묶음이 직렬화 바이트까지 같은지(정렬 키·같은 인코딩)."""
    def _b(x):
        return json.dumps(x, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return _b(_legacy_view(old)) == _b(_legacy_view(new))


def paragraph_diff(old_laws: dict, new_laws: dict) -> dict[str, str]:
    """v0.66.0 저장 게이트 — 항별 데이터(`paragraphs`·항별 전용 레코드·그 조항)가 기존과 다른 법령 {id: 요약}.

    --accept-paragraphs 가 있어야 저장한다. 조문 단위 기존 필드의 차이는 diff_against_existing이 따로 잡는다.
    """
    out: dict[str, str] = {}
    for rid, new in new_laws.items():
        old = old_laws.get(rid) if isinstance(old_laws.get(rid), dict) else {}
        o, n = _paragraph_view(old.get("articles")), _paragraph_view(new.get("articles"))
        if o != n:
            changed = sum(1 for k in set(o) | set(n) if o.get(k) != n.get(k))
            out[rid] = f"항별 데이터 {changed}개 조문 차이"
    return out


LEGACY_DIFF_PREFIX = "같은 판본에서 조문 레코드"


def diff_against_existing(old_laws: dict, new_laws: dict) -> dict[str, str]:
    """저장 게이트 G2 — 기존 스냅샷과 다른 법령 {rule_set_id: 사유}. 같은 판본이면 조문 레코드가 같고 조항이 줄지 않아야 한다.

    사유가 LEGACY_DIFF_PREFIX로 시작하면(같은 판본에서 조문 단위 기존 필드 차이) 호출부는 --accept-diff와 무관하게 중단한다.
    """
    out: dict[str, str] = {}
    for rid, new in new_laws.items():
        old = old_laws.get(rid)
        if not isinstance(old, dict):
            out[rid] = "새 법령"
            continue
        if (old.get("mst"), old.get("efyd")) != (new.get("mst"), new.get("efyd")):
            out[rid] = f"판본 변경 {old.get('mst')}·{old.get('efyd')} → {new.get('mst')}·{new.get('efyd')}"
            continue
        # v0.66.0: 조문 단위 기존 필드만 바이트 대조(항별 `paragraphs`·항별 전용 레코드는 paragraph_diff가 본다).
        if not legacy_bytes_equal(old.get("articles") or {}, new.get("articles") or {}):
            o, n = _legacy_view(old.get("articles")), _legacy_view(new.get("articles"))
            changed = sum(1 for k in set(o) | set(n) if o.get(k) != n.get(k))
            out[rid] = f"{LEGACY_DIFF_PREFIX} {changed}건 차이"
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


_PLAN_TARGET = 119  # 계획서 4-2 재측정(2026-11-09) 대상 수 — 15% 넘게 벗어나면 보고서에 경고


def _tier(resp: dict) -> int:
    if resp.get("content_format") == "oversized_pointer":
        return 3
    return 2 if resp.get("structure_omitted") else 1


def _paragraph_report(payload: dict, law_details: dict, pst: dict, group_dist: dict, para_fail: dict,
                      para_targets: dict, para_out1: list, single_same: int, single_differs: list,
                      record_absent: list, para_clause_missing: dict) -> tuple[list[str], int, set]:
    """v0.66.0 결박 수치 보고(계획서 5-3) — (보고서 줄, 항별 블록으로 크기 단계가 바뀐 조문 수, 교집합).

    크기 단계는 서버와 같은 조립 함수(article_history.notice_from_snapshot·main._build_article_detail)로 서빙
    본문의 모든 조문에 대해 잰다: 안내 없음 → 새 안내, 기존 문장 → 기존 문장 + 항별 블록.
    """
    from korean_rnd_regs_mcp import article_history as ah
    from korean_rnd_regs_mcp.main import _article_unit_id, _build_article_detail, _resolve_effective_date

    parsed = ah._parse_snapshot(payload)
    snap, load_stats = parsed if parsed else ({"generated_date": "", "laws": {}}, {"articles": 0, "paragraphs": 0, "dropped": 0})
    n_all = 0
    none_full = base_full = none_base = 0
    changed_ids: list[str] = []
    max_resp = max_notice = max_block = 0
    raw_over_cap = omitted = staged_targets = 0
    rows: list[str] = []
    for rid, (rs, resolved, detail, dup) in sorted(law_details.items()):
        mst = resolved.doc_id
        efyd_raw = detail.get("시행일자", "")
        eff = _resolve_effective_date(rs, resolved)
        seen: set[str] = set()
        for art in detail.get("articles", []):
            uid = _article_unit_id(art)
            if uid is None or uid in seen:
                continue
            seen.add(uid)
            n_all += 1
            full_n = ah.notice_from_snapshot(snap, rid, uid, mst, efyd_raw, "eflaw", eff)
            base_n = ah.notice_from_snapshot(snap, rid, uid, mst, efyd_raw, "eflaw", eff, with_paragraphs=False)
            pid = f"law:{mst}:{uid}"
            r_none = _build_article_detail(pid, uid, rs, art, eff)
            r_base = _build_article_detail(pid, uid, rs, art, eff, article_notice=base_n)
            r_full = _build_article_detail(pid, uid, rs, art, eff, article_notice=full_n)
            t0, t1, t2 = _tier(r_none), _tier(r_base), _tier(r_full)
            none_full += t0 != t2
            none_base += t0 != t1
            if t1 != t2:
                base_full += 1
                changed_ids.append(f"{rid}|{uid}")
            size = len(json.dumps(r_full, ensure_ascii=False))
            max_resp = max(max_resp, size)
            max_notice = max(max_notice, len(full_n))
            key = f"{rid}|{uid}"
            if key in para_targets:
                block = full_n[len(base_n) + 1:] if full_n != base_n else ""
                max_block = max(max_block, len(block))
                omitted += ah._PARA_OMITTED in block
                rec = snap["laws"].get(rid, {}).get("articles", {}).get(uid) or {}
                law = snap["laws"].get(rid, {})
                if rec.get("paragraphs"):
                    raw = ah._assemble_block(rec, rec["paragraphs"], law.get("clauses") or {}, None, True)
                    raw_over_cap += len(raw) > ah._PARA_BLOCK_MAX_CHARS
                staged_g = sum(1 for g in rec.get("paragraphs") or [] if g.get("staged_dates"))
                staged_targets += staged_g > 0
                rows.append(f"| {key} | {para_targets[key]} | {staged_g} | {len(block)} | {len(full_n)} | {size} | "
                            f"{t1}→{t2} |")
    overlap = set(para_targets) & (set(para_fail) | set(single_differs))
    # 분리 시행 그룹의 조항 상태 — 추출 대상(제정·일부개정·전부개정) 중 미수록과, 조항 없이 목록 문장으로 나가는 그룹
    staged_groups = listed = listed_other = extract_targets = 0
    for rid, law in (payload.get("laws") or {}).items():
        extract_targets += len(paragraph_clause_targets(law.get("articles") or {}))
        keys = set(law.get("clauses") or {})
        for rec in (law.get("articles") or {}).values():
            for g in rec.get("paragraphs") or []:
                if not g.get("staged_dates"):
                    continue
                staged_groups += 1
                if f"{g['promulgation_no']}|{g['promulgation_date']}" not in keys:
                    listed += 1
                    listed_other += g.get("amendment_kind") == "타법개정"
    n_ge2 = sum(1 for v in para_targets.values() if v >= 2)
    n_target = len(para_targets)
    dev = abs(n_target - _PLAN_TARGET) / _PLAN_TARGET
    marked = pst["self_markers"]
    pct = f"{pst['latest_match'] / marked * 100:.1f}%" if marked else "-"
    fail_by: dict[str, int] = {}
    for why in para_fail.values():
        fail_by[why] = fail_by.get(why, 0) + 1
    lines = [
        "## 항별 개정 표지(v0.66.0 결박 수치)",
        "",
        f"- 항 자기 표지 {marked}개 · 날짜 2개 이상 {pst['multi_date']}개 · 가장 늦은 날짜가 이력 공포일과 일치 "
        f"{pst['latest_match']}/{marked}({pct}) · 첫 날짜 일치 {pst['first_match']} · 어느 쪽도 아님 {pst['neither']}",
        f"- 한 항 다중 표지 {pst['multi_marker_paras']} · 호·목 표지만 있는 항 {pst['sub_only_paras']}(번호 있는 항) + "
        f"{pst['sub_only_wrappers']}(번호·본문 없이 호만 묶는 항, 호 표지 기준) · "
        f"호·목 표지가 항 표지보다 늦은 항 {pst['sub_later_paras']}",
        f"- 전부 대응 조문의 그룹 수 분포: {dict(sorted(group_dist.items()))}",
        f"- 대응 실패 조문 {len(para_fail)}건: {dict(sorted(fail_by.items()))}",
        f"- 대상 {n_target} = 그룹 2개 이상 {n_ge2} + 스냅샷 밖 1그룹 {len(para_out1)} · 그중 분리 시행 그룹 보유 "
        f"{staged_targets} · 계획 119 대비 {dev * 100:.1f}%" + (" ★15% 초과 — 원인 확인 필요" if dev > 0.15 else ""),
        f"- 그룹 1개: 조문 레코드와 같음 {single_same}(붙이지 않음) · 다름 {len(single_differs)}(붙이지 않음) "
        f"{sorted(single_differs)}",
        f"- 레코드 공포번호가 어느 그룹에도 없는 대상 {len(record_absent)}건: {sorted(record_absent)}",
        f"- 대상 ∩ (대응 실패 ∪ 그룹 1개 다름) = {len(overlap)}건" + (f" {sorted(overlap)}" if overlap else ""),
        f"- 로더 재검사: 조문 {load_stats['articles']}, paragraphs {load_stats['paragraphs']}, 형식 탈락 "
        f"{load_stats['dropped']}",
        f"- 크기 단계(서빙 본문 {n_all}개 조문): 기존 문장→기존+항별 블록 변화 {base_full}건"
        f"{' ' + str(changed_ids) if changed_ids else ''} · 안내 없음→새 안내 변화 {none_full}건 · 안내 없음→기존 문장 "
        f"변화 {none_base}건 · 최대 응답 직렬화 {max_resp}자 · 최대 안내 {max_notice}자 · 최대 항별 블록 {max_block}자 · "
        f"1,500자 상한 축약 발동 {raw_over_cap}건(그룹 생략 {omitted}건)",
        f"- 항별 분리 시행 그룹 {staged_groups}개: 조항 추출 대상 {extract_targets}개 중 미수록 {len(para_clause_missing)} · "
        f"조항 없이 목록 문장으로 나가는 그룹 {listed}(그중 타법개정 {listed_other})",
        f"- 다중 날짜 신설 표지 → 개정 재라벨 {pst['relabel_new_to_amend']}",
        "",
        "### 대응 실패 조문",
        "",
        *([f"- {k}: {v}" for k, v in sorted(para_fail.items())] or ["- 없음"]),
        "",
        "### 항별 조항 없는 분리 시행 그룹",
        "",
        *([f"- {k}: {v}" for k, v in sorted(para_clause_missing.items())] or ["- 없음"]),
        "",
        "### 대상 조문(그룹 수·분리 시행 그룹 수·블록 길이·안내 길이·응답 직렬화 길이·크기 단계 기존→새)",
        "",
        "| 조문 | 그룹 | 분리 | 블록 | 안내 | 응답 | 단계 |",
        "|---|---|---|---|---|---|---|",
        *rows,
    ]
    return lines, base_full, overlap, load_stats["dropped"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--require-all-clauses", action="store_true",
                    help="대상 조문 중 부칙 시행일 조항이 없는 것이 하나라도 있으면 저장하지 않음")
    ap.add_argument("--accept-diff", default="",
                    help="판본(mst·efyd)이 바뀐 법령·새 법령, 같은 판본의 조항 감소·원문 변경을 허용할 rule_set_id 목록"
                         "(쉼표 구분). 같은 판본에서 조문 단위 기존 필드가 달라진 법령은 이 플래그로도 저장하지 않음")
    ap.add_argument("--accept-paragraphs", action="store_true",
                    help="항별 데이터(paragraphs·항별 전용 레코드)의 추가·변경을 허용(조문 단위 기존 필드는 그대로여야 함)")
    args = ap.parse_args(argv)
    accept = {s.strip() for s in args.accept_diff.split(",") if s.strip()}
    save = not args.dry_run and not args.ids  # 일부 법령만 지정한 실행은 저장하지 않는다

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    from korean_rnd_regs_mcp.live_api import LawApiClient, LawApiError
    from korean_rnd_regs_mcp.main import _article_amendment_history, _article_unit_id, _resolve_effective_date
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
    # v0.66.0 항별 표지 집계(보고서 결박 수치)
    pst = {"self_markers": 0, "multi_date": 0, "multi_marker_paras": 0, "sub_only_paras": 0, "sub_later_paras": 0,
           "sub_only_wrappers": 0, "relabel_new_to_amend": 0, "latest_match": 0, "first_match": 0, "neither": 0}
    group_dist: dict[int, int] = {}
    para_fail: dict[str, str] = {}      # "rid|JO…" → 사유
    para_targets: dict[str, int] = {}   # "rid|JO…" → 그룹 수
    para_out1: list[str] = []           # 대상 중 스냅샷 밖(조문 단위 레코드 없음) 1그룹
    single_same = 0
    single_differs: list[str] = []
    record_absent: list[str] = []
    para_clause_missing: dict[str, str] = {}
    law_details: dict[str, tuple] = {}  # rid → (rs, resolved, detail) — 크기 단계 전수 확인용
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
                out = {"uid": None, "rec": None, "why": "", "groups": [], "pwhy": "ok", "pstats": None,
                       "pub_dates": set()}
                uid = _article_unit_id(art)
                if uid is None:
                    out["why"] = "JO 인코딩 불가"
                    return out
                out["uid"] = uid
                digits = uid[2:]
                jo6 = digits if len(digits) == 6 else digits + "00"
                try:
                    entries = fetch_article_history(client, law_id, jo6)
                except LawApiError as e:
                    out["why"] = f"이력 조회 실패({e.code})"
                    return out
                chosen, why = select_entry(entries, jo6, efyd)
                if chosen is not None:
                    why = stage_gate(chosen, entries, rows, efyd)
                if why == "ok":
                    why = marker_gate(chosen, _article_amendment_history(art), art.get("조문내용", ""))
                out["why"] = why
                if why == "ok":
                    out["rec"] = build_record(chosen, stage_dates_for(rows, chosen.get("법령일련번호", "")))
                # v0.66.0 항별 표지 — 같은 이력 응답만 쓴다(추가 조회 없음).
                markers, pwhy, pstats = paragraph_markers(art)
                out["pstats"] = pstats
                out["pub_dates"] = {e.get("공포일자", "") for e in entries}
                if markers is None:
                    out["pwhy"] = pwhy
                else:
                    groups, gwhy = match_paragraphs(markers, entries, jo6, rows)
                    out["pwhy"] = gwhy
                    out["groups"] = groups or []
                return out

            with ThreadPoolExecutor(max_workers=6) as ex:
                results = list(ex.map(_one, detail.get("articles", [])))
            # 같은 JO가 본문에 두 번 나오면 서버가 서빙하는 쪽(첫 번째)과 검증한 쪽이 다를 수 있다 — 제외.
            seen_uid: dict[str, int] = {}
            for r in results:
                if r["uid"] is not None:
                    seen_uid[r["uid"]] = seen_uid.get(r["uid"], 0) + 1
            dup = {u for u, n in seen_uid.items() if n > 1}
            for r in results:
                if r["uid"] in dup:
                    r.update(rec=None, why="조문 번호 중복", groups=[], pwhy="조문 번호 중복")
            for r in results:
                if r["rec"] is None:
                    excl[r["why"]] = excl.get(r["why"], 0) + 1
                else:
                    arts[r["uid"]] = r["rec"]
            # v0.66.0 항별 그룹 — 붙이기 판단과 집계
            for r in results:
                ps = r["pstats"]
                if ps is None or r["uid"] in dup:
                    continue
                for k in ("self_markers", "multi_date", "multi_marker_paras", "sub_only_paras", "sub_later_paras",
                          "sub_only_wrappers", "relabel_new_to_amend"):
                    pst[k] += ps[k]
                for latest8, first8 in ps["marker_dates"]:
                    hit_l, hit_f = latest8 in r["pub_dates"], first8 in r["pub_dates"]
                    pst["latest_match"] += hit_l
                    pst["first_match"] += hit_f
                    pst["neither"] += not (hit_l or hit_f)
                key = f"{rs.id}|{r['uid']}"
                if r["pwhy"] != "ok":
                    para_fail[key] = r["pwhy"]
                    continue
                groups = r["groups"]
                if not groups:
                    continue
                group_dist[len(groups)] = group_dist.get(len(groups), 0) + 1
                decision = paragraph_decision(groups, r["rec"])
                if decision == "single_same":
                    single_same += 1
                elif decision == "single_differs":
                    single_differs.append(key)
                elif decision == "attach":
                    para_targets[key] = len(groups)
                    if r["rec"] is None:
                        arts[r["uid"]] = {"paragraphs": groups}
                        if len(groups) == 1:
                            para_out1.append(key)
                    else:
                        r["rec"]["paragraphs"] = groups
                        if not any(_num_eq(g["promulgation_no"], r["rec"]["promulgation_no"]) for g in groups):
                            record_absent.append(key)
            entry = {"mst": resolved.doc_id, "efyd": _iso(efyd), "law_id": law_id, "articles": arts}
            note = ""
            units = None
            clauses: dict = {}
            if clause_targets(arts):
                units = fetch_buchik_units(client, resolved.doc_id, efyd, law_id)
                clauses, missing = build_clauses(arts, units, client.api_key)
                clause_targets_n += len(clause_targets(arts))
                for uid, why in missing.items():
                    clause_missing[f"{rs.id}|{uid}"] = why
                note = f" · 부칙 조항 {len(clauses)}건(대상 {len(clause_targets(arts))}, 미수록 {len(missing)})"
            ptargets = paragraph_clause_targets(arts)
            if ptargets:
                # 항별 그룹의 조항은 못 붙여도 저장을 막지 않는다(런타임이 목록 문장으로 낸다).
                try:
                    if units is None:
                        units = fetch_buchik_units(client, resolved.doc_id, efyd, law_id)
                    added, pmissing = build_paragraph_clauses(arts, units, clauses, client.api_key)
                except LawApiError as e:
                    added, pmissing = {}, {tid: f"부칙 조회 실패({e.code})" for tid in ptargets}
                clauses.update(added)
                for tid, why in pmissing.items():
                    para_clause_missing[f"{rs.id}|{tid}"] = why
                note += f" · 항별 조항 추가 {len(added)}건(항별 대상 {len(ptargets)}, 미수록 {len(pmissing)})"
            if clauses:
                entry["clauses"] = clauses
            laws[rs.id] = entry
            law_details[rs.id] = (rs, resolved, detail, dup)
            staged = sum(1 for a in arts.values() if "staged_dates" in a)
            n_legacy = sum(1 for a in arts.values() if "promulgation_no" in a)
            n_para = sum(1 for a in arts.values() if a.get("paragraphs"))
            n = len(detail.get("articles", []))
            report.append(f"| {rs.id} | {n_legacy}/{n} | 분리 시행 {staged} · 항별 {n_para} · "
                          f"제외 {dict(sorted(excl.items()))}{note} |")
            for k, v in excl.items():
                excluded_total[k] = excluded_total.get(k, 0) + v
            print(f"{rs.id}: {n_legacy}/{n} staged={staged} paragraphs={n_para}", flush=True)
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
    total = sum(1 for v in laws.values() for a in v["articles"].values() if "promulgation_no" in a)
    para_only = sum(1 for v in laws.values() for a in v["articles"].values() if "promulgation_no" not in a)
    n_clauses = sum(len(v.get("clauses") or {}) for v in laws.values())
    fetch_failures = sum(v for k, v in excluded_total.items() if k.startswith("이력 조회 실패"))
    para_lines, tier_block_changes, overlap, reload_dropped = _paragraph_report(
        json.loads(json_text), law_details, pst, group_dist, para_fail, para_targets, para_out1, single_same,
        single_differs, record_absent, para_clause_missing)

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
    # 같은 판본에서 조문 단위 기존 필드가 달라진 법령은 --accept-diff로도 허용하지 않는다(판본 변경만 그 플래그 대상).
    legacy_hard = {rid: why for rid, why in diffs.items() if why.startswith(LEGACY_DIFF_PREFIX)}
    if legacy_hard:
        blocks.append("같은 판본에서 조문 단위 기존 필드 차이(어떤 플래그로도 저장 불가 — 원인 확인 필요): "
                      + "; ".join(f"{rid} {why}" for rid, why in sorted(legacy_hard.items())))
    unaccepted = {rid: why for rid, why in diffs.items() if rid not in accept and rid not in legacy_hard}
    if unaccepted:
        blocks.append("기존 스냅샷과 차이(--accept-diff 필요): "
                      + "; ".join(f"{rid} {why}" for rid, why in sorted(unaccepted.items())))
    if args.require_all_clauses and clause_missing:
        blocks.append(f"부칙 시행일 조항 미수록 {len(clause_missing)}건")
    # v0.66.0: 항별 데이터의 추가·변경은 명시 플래그로만(조문 단위 기존 필드 차이는 위 게이트가 잡는다).
    pdiffs = paragraph_diff(old_laws, laws) if not args.ids else {}
    if pdiffs and not args.accept_paragraphs:
        blocks.append(f"항별 데이터 차이 {len(pdiffs)}개 법령(--accept-paragraphs 필요)")
    if overlap:
        blocks.append(f"항별 대상과 대응 실패·불일치 집합의 교집합 {len(overlap)}건")
    if reload_dropped:
        blocks.append(f"생성한 항별 데이터를 런타임 로더가 {reload_dropped}건 버림(형식 탈락 J>0)")
    if tier_block_changes:
        blocks.append(f"항별 블록으로 크기 단계가 바뀐 조문 {tier_block_changes}건(상한 하향 필요)")

    lines = [
        "# 조문별 변경 이력 스냅샷 생성 보고",
        "",
        f"- 생성: {now} · 법령 {len(laws)}/{len(targets)} 수록 · 조문 {total}건 · 항별 전용 레코드 {para_only}건 · "
        f"미수록 법령 {failed}",
        f"- 제외 사유 합계: {dict(sorted(excluded_total.items()))}",
        f"- 부칙 시행일 조항: 대상 {clause_targets_n}건 · 수록 조항 {n_clauses}개 · 조항 없는 대상 {len(clause_missing)}건",
        f"- 기존 스냅샷과 차이: {dict(sorted(diffs.items())) or '없음'} · 항별 데이터 차이: "
        f"{dict(sorted(pdiffs.items())) or '없음'}",
        f"- JSON sha256: {hashlib.sha256(json_text.encode('utf-8')).hexdigest()}",
        "",
        "| rule_set_id | 수록/전체 조문 | 비고 |",
        "|---|---|---|",
        *report,
        "",
        *para_lines,
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
    print("\n".join(ln for ln in para_lines if not ln.startswith("| ")))
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
