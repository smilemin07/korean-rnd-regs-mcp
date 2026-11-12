"""조문별 변경 이력 스냅샷 로더·안내 문장 조립 (v0.60.0, law 조문 상세 전용).

데이터는 배포 전 `scripts/extract_article_history.py`가 만든 `article_history.json`뿐이다 — 런타임
네트워크 호출은 없다. 로드는 첫 사용 때 1회(lazy)이며, 파일 누락·손상은 빈 스냅샷으로 대체하고
WARNING 1회만 남긴다(본문 응답 무영향). 레코드 하나가 형식에 맞지 않으면 그 레코드만 버린다.

스냅샷은 생성 시점의 서빙 판본(mst·efyd)에 묶인다. 호출부는 서빙 판본이 같을 때만 조문별 문장을
쓰고, 다르면 일반 문장으로 내려간다 — 낡은 스냅샷이 다른 판본의 날짜를 단정하지 않게 한다.

v0.63.0: 분리 시행 판본 조문의 문장에 그 개정의 부칙 시행일 조항 원문을 싣는다(법령별 `clauses`,
키 = 레코드의 "공포번호|공포일"). 조항 하나가 형식에 맞지 않으면 그 조항만 버리고, 조항이 없거나
조립에 실패하면 v0.60.0 분리 시행 문장으로 내려간다. 해석·날짜 계산은 서버가 하지 않는다.

v0.66.0: 항 본문 끝 개정 표지(예 `<개정 2017.7.26, 2025.12.30>`)와 대응한 개정 판본을 공포번호별
그룹으로 담은 `paragraphs`를 읽어, 기존 문장 뒤에 줄바꿈으로 항별 블록을 덧붙인다. 조문 단위 레코드가
없는 조문은 `paragraphs`만 가진 레코드로 온다(일반 문장 + 항별 블록). `paragraphs` 형식이 어긋나면 그
조문의 `paragraphs`만 버린다. 블록 조립이 실패하면 기존 문장만 낸다(never-raise).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger("rnd-regs-mcp.article_history")

_DATA_PATH = Path(__file__).parent / "article_history.json"
_SCHEMA_VERSION = 1
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LAW_KIND = re.compile(r"^(?:법률|대통령령|총리령|[가-힣]{1,12}부령)$")
_CHANGE_REASONS = frozenset({"제정", "조문변경", "본조신설", "전부개정"})
_JO_KEY = re.compile(r"^JO\d{4}(?:\d{2})?$")
_MAX_STAGES = 6
# v0.63.0 부칙 시행일 조항: 키는 레코드의 공포번호·공포일 문자열 그대로(앞 0 포함 — 대상 18쌍 중 3쌍).
_CLAUSE_KEY = re.compile(r"^\d{1,8}\|\d{4}-\d{2}-\d{2}$")
_CLAUSE_MAX_CHARS = 600  # 생성기(extract_article_history._CLAUSE_MAX_CHARS)와 같은 상한
_CLAUSE_BAD_CHARS = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")  # 줄바꿈(\n) 외 제어문자
# v0.66.0 항별 그룹
_PARA_LABELS = frozenset({"개정", "신설", "삭제"})
_PARA_NO = re.compile(r"^[1-9]\d?$")  # "1"~"99"(생성기 _MAX_PARA_NO와 같은 범위)
_AMENDMENT_KIND = re.compile(r"^[가-힣]{0,10}$")
_MAX_GROUPS = 12
_MAX_ITEMS = 60
_PARA_BLOCK_MAX_CHARS = 1500  # 항별 블록(조항 원문 포함) 상한 — 계획서 5-2

_lock = threading.Lock()
_snapshot: dict | None = None

# 스냅샷 불일치 INFO 로그 — 규정별 시간당 1회(키 = rule_set_id, 항목 수는 규정 수 수준).
_MISMATCH_LOG_INTERVAL_S = 3600.0
_mismatch_last: dict[str, float] = {}
_mismatch_lock = threading.Lock()

# (c) 일반 문장 — 조문별 근거가 없을 때 모든 경로(레코드 없음·판본 불일치·스냅샷 손상·조립 실패·호출부 예외)가
# 이 하나를 쓴다(v0.66.0: 호스트에게 연혁 조회를 지시하던 문장을 사용자 안내형으로 바꿈).
_GENERAL_NOTICE_TEMPLATE = (
    "effective_date({eff_date})는 조회된 법령 판본 전체의 시행일이며, 이 조문의 시행일과 같다는 뜻은 아닙니다. "
    "개정 판본의 시행일은 이 조문이 처음 시행된 날과 다를 수 있으므로, 이 응답의 근거만으로 이 조문이 처음 "
    "시행된 날을 단정하지 마십시오. 필요하면 사용자가 국가법령정보센터의 조문 연혁과 부칙에서 확인하도록 "
    "안내하십시오."
)

# v0.63.0 조항 판단 안내(분리 시행 문장과 항별 블록이 같은 문구를 쓴다).
_CLAUSE_GUIDANCE = (
    "단서가 항·호나 '…에 관한 부분'처럼 조문 일부에만 걸리면 부분별로 나누어 답하십시오. 단서가 이 조문이 아닌 "
    "다른 조문만 들면 이 조문에는 본문의 시행일이 적용됩니다. 조문 번호는 가지 번호(예: 제17조의2)까지 같을 때만 "
    "해당합니다. '공포 후 N개월' 같은 기간은 위 시행일 목록에서 대응하는 날짜를 고르고, 목록에 없는 날짜를 계산해 "
    "만들지 마십시오. 목록 중 아직 오지 않은 날짜는 시행 예정일입니다. 위 원문만으로 정할 수 없으면 한 날짜로 "
    "단정하지 마십시오."
)

_PARA_HEAD = (
    "항별 개정 표지 기준(각 항 끝 표지에 적힌 날짜 중 가장 최근 날짜, 공포일): 아래 날짜는 각 표지와 대응하는 "
    "개정 판본의 시행일이며 이 조문이 처음 시행된 날이 아닙니다. 표지가 없는 항·호의 개정 여부는 말하지 않습니다."
)
_PARA_OMITTED = "그 밖의 항의 표지 대응은 길이 제한으로 생략했습니다."


def _valid_date(s: object) -> bool:
    if not isinstance(s, str) or not _ISO_DATE.match(s):
        return False
    try:
        time.strptime(s, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _valid_no(no: object) -> bool:
    return isinstance(no, str) and no.isascii() and no.isdigit() and 1 <= len(no) <= 8


def _clean_article(rec: object) -> dict | None:
    """레코드 1건 검증 — 통과하면 필요한 필드만 담은 새 dict, 아니면 None."""
    if not isinstance(rec, dict):
        return None
    kind = rec.get("law_kind")
    no = rec.get("promulgation_no")
    reason = rec.get("change_reason")
    pd = rec.get("promulgation_date")
    ved = rec.get("version_effective_date")
    if not (isinstance(kind, str) and _LAW_KIND.match(kind)):
        return None
    if not (isinstance(no, str) and no.isascii() and no.isdigit() and len(no) <= 8):
        return None
    if not isinstance(reason, str) or reason not in _CHANGE_REASONS or not _valid_date(pd) or not _valid_date(ved):
        return None
    out = {"law_kind": kind, "promulgation_no": no, "change_reason": reason,
           "promulgation_date": pd, "version_effective_date": ved}
    staged = rec.get("staged_dates")
    if staged is not None:
        if not (isinstance(staged, list) and 2 <= len(staged) <= _MAX_STAGES and all(_valid_date(d) for d in staged)):
            return None
        out["staged_dates"] = list(staged)
    return out


def _clean_group(g: object) -> dict | None:
    """항별 그룹 1개 검증 — 통과하면 필요한 필드만 담은 새 dict, 아니면 None."""
    if not isinstance(g, dict):
        return None
    kind, no, pd, ved = g.get("law_kind"), g.get("promulgation_no"), g.get("promulgation_date"), g.get("version_effective_date")
    ak = g.get("amendment_kind", "")
    # 새 필드는 fullmatch(정규식 `$`가 허용하는 끝 줄바꿈까지 거절 — Redteam diff).
    if not (isinstance(kind, str) and _LAW_KIND.fullmatch(kind) and _valid_no(no) and _valid_date(pd) and _valid_date(ved)):
        return None
    if not (isinstance(ak, str) and _AMENDMENT_KIND.fullmatch(ak)):
        return None
    items = g.get("items")
    if not (isinstance(items, list) and 1 <= len(items) <= _MAX_ITEMS):
        return None
    clean_items = []
    for it in items:
        if not (isinstance(it, list) and len(it) == 2 and isinstance(it[0], str) and _PARA_NO.fullmatch(it[0])
                and isinstance(it[1], str) and it[1] in _PARA_LABELS):
            return None
        clean_items.append((int(it[0]), it[1]))
    out = {"law_kind": kind, "promulgation_no": no, "promulgation_date": pd, "amendment_kind": ak,
           "version_effective_date": ved, "items": clean_items}
    staged = g.get("staged_dates")
    if staged is not None:
        if not (isinstance(staged, list) and 2 <= len(staged) <= _MAX_STAGES and all(_valid_date(d) for d in staged)):
            return None
        out["staged_dates"] = list(staged)
    return out


def _clean_paragraphs(raw: object) -> list | None:
    """`paragraphs` 검증 — 그룹 하나라도 어긋나거나 항 번호·공포번호가 겹치면 None(그 조문의 항별 데이터 전체를 버림)."""
    if not (isinstance(raw, list) and 1 <= len(raw) <= _MAX_GROUPS):
        return None
    groups = []
    seen_no: set[int] = set()
    seen_para: set[int] = set()
    for g in raw:
        c = _clean_group(g)
        if c is None:
            return None
        pno = int(c["promulgation_no"])
        if pno in seen_no:
            return None
        seen_no.add(pno)
        for n, _label in c["items"]:
            if n in seen_para:
                return None
            seen_para.add(n)
        groups.append(c)
    return groups


def _clean_clauses(raw: object) -> dict:
    """법령의 부칙 시행일 조항 → {"공포번호|공포일": 원문}. 형식에 맞는 항목만 남긴다(나머지는 그 항목만 버림)."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        if not (isinstance(key, str) and _CLAUSE_KEY.match(key) and _valid_date(key.split("|", 1)[1])
                and isinstance(val, dict)):
            continue
        text = val.get("text")
        if not isinstance(text, str):
            continue
        text = text.strip()
        if not text or len(text) > _CLAUSE_MAX_CHARS or _CLAUSE_BAD_CHARS.search(text):
            continue
        if "OC=" in text or "http" in text.lower():
            continue
        out[key] = text
    return out


def _clean_record(rec: object) -> tuple[dict | None, bool]:
    """조문 레코드 1건 → (정제 레코드 또는 None, 항별 데이터를 형식 검사로 버렸는지).

    조문 단위 필드가 있으면 기존 검사(_clean_article)를 그대로 쓰고, `paragraphs`가 어긋나면 그것만 버린다.
    조문 단위 필드가 없으면 `paragraphs`만 가진 레코드(v0.66.0)로 받는다 — 어긋나면 레코드가 남지 않는다.
    """
    if not isinstance(rec, dict):
        return None, False
    has_para = "paragraphs" in rec
    if set(rec) == {"paragraphs"}:
        paras = _clean_paragraphs(rec["paragraphs"])
        return ({"paragraphs": paras} if paras is not None else None), paras is None
    base = _clean_article(rec)
    if base is None:
        return None, has_para
    if has_para:
        paras = _clean_paragraphs(rec["paragraphs"])
        if paras is None:
            return base, True
        base["paragraphs"] = paras
    return base, False


def _parse_snapshot(raw: object) -> tuple[dict, dict] | None:
    """JSON 값 → (스냅샷, 집계 {"articles","paragraphs","dropped"}). 최상위 형식 이상이면 None."""
    if not isinstance(raw, dict) or raw.get("schema") != _SCHEMA_VERSION or not isinstance(raw.get("laws"), dict):
        return None
    gen = raw.get("generated_at")
    gen_date = gen[:10] if isinstance(gen, str) and _valid_date(gen[:10]) else ""
    laws: dict = {}
    stats = {"articles": 0, "paragraphs": 0, "dropped": 0}
    for rid, law in raw["laws"].items():
        if not (isinstance(rid, str) and isinstance(law, dict)):
            continue
        mst, efyd, arts = law.get("mst"), law.get("efyd"), law.get("articles")
        if not (isinstance(mst, str) and mst.isascii() and mst.isdigit() and _valid_date(efyd) and isinstance(arts, dict)):
            continue
        clean = {}
        for jo, rec in arts.items():
            if not (isinstance(jo, str) and _JO_KEY.match(jo)):
                continue
            c, dropped = _clean_record(rec)
            if dropped:
                stats["dropped"] += 1
            if c is not None:
                clean[jo] = c
                if "promulgation_no" in c:
                    stats["articles"] += 1
                if c.get("paragraphs"):
                    stats["paragraphs"] += 1
        laws[rid] = {"mst": mst, "efyd": efyd, "articles": clean, "clauses": _clean_clauses(law.get("clauses"))}
    return {"generated_date": gen_date, "laws": laws}, stats


def _load_uncached(path: Path) -> dict:
    """파일 → {"generated_date": str, "laws": {rule_set_id: {"mst","efyd","articles","clauses"}}}. 실패 시 빈 스냅샷."""
    empty = {"generated_date": "", "laws": {}}
    try:
        parsed = _parse_snapshot(json.loads(path.read_text(encoding="utf-8")))
        if parsed is None:
            logger.warning("article_history: 스냅샷 형식 이상 — 조문별 변경 이력 안내 없이 동작")
            return empty
        snap, stats = parsed
        level = logging.WARNING if stats["dropped"] else logging.INFO
        logger.log(level, "article_history: 조문 %d, paragraphs %d, 형식 탈락 %d",
                   stats["articles"], stats["paragraphs"], stats["dropped"])
        return snap
    except Exception as exc:  # noqa: BLE001 — 누락·손상 어느 쪽도 응답을 막지 않는다
        logger.warning("article_history: 스냅샷 로드 실패(%s) — 조문별 변경 이력 안내 없이 동작", type(exc).__name__)
        return empty


def load_snapshot() -> dict:
    """lazy 싱글턴(double-checked lock). 실패해도 빈 스냅샷을 돌려준다(never-raise)."""
    global _snapshot
    snap = _snapshot
    if snap is not None:
        return snap
    with _lock:
        if _snapshot is None:
            _snapshot = _load_uncached(_DATA_PATH)
        return _snapshot


def _reset_for_tests(path: Path | None = None) -> None:
    """테스트 전용 — 캐시를 비우고(선택) 다른 경로에서 다시 읽게 한다."""
    global _snapshot, _DATA_PATH
    with _lock:
        _snapshot = None
        if path is not None:
            _DATA_PATH = path
    with _mismatch_lock:
        _mismatch_last.clear()


def _log_mismatch(rule_set_id: str) -> None:
    now = time.monotonic()
    with _mismatch_lock:
        last = _mismatch_last.get(rule_set_id)
        if last is not None and now - last < _MISMATCH_LOG_INTERVAL_S:
            return
        _mismatch_last[rule_set_id] = now
    logger.info("event=article_history_snapshot_mismatch rule_set_id=%s", rule_set_id)


def general_notice(eff_date: str) -> str:
    """일반 안내 문장(조문별 근거가 없을 때) — 호출부의 예외 분기에서도 쓴다."""
    return _general_sentence(eff_date)


def _general_sentence(eff_date: str) -> str:
    return _GENERAL_NOTICE_TEMPLATE.format(eff_date=eff_date)


def _staged_sentence(head: str, staged: list, tail: str) -> str:
    """v0.60.0 분리 시행 문장 — 조항이 없거나 조항 문장 조립에 실패했을 때 쓴다."""
    return (
        f"{head}입니다. 그 판본의 시행일이 {'·'.join(staged)}로 나뉘어 있어, 이 조문의 시행일은 이 응답으로 "
        f"정할 수 없으니 그 부칙에서 확인하십시오.{tail}"
    )


def _staged_clause_sentence(head: str, staged: list, clause: str, tail: str) -> str:
    """v0.63.0 분리 시행 문장 + 그 개정의 부칙 시행일 조항 원문(줄바꿈으로 앞뒤 경계를 고정)."""
    return (
        f"{head}입니다. 그 판본의 시행일은 {'·'.join(staged)}로 나뉘어 있습니다. "
        f"그 개정의 부칙 시행일 조항 원문은 다음과 같습니다.\n{clause}\n"
        f"이 원문은 위 최근 개정으로 바뀐 부분의 시행일을 정합니다. {_CLAUSE_GUIDANCE}{tail}"
    )


def _base_sentence(snap: dict, law: dict, rec: dict, eff_date: str) -> tuple[str, str | None]:
    """조문 단위 문장(a/b) 또는 항별 전용 레코드의 일반 문장(c) → (문장, 그 문장에 실은 조항 키 또는 None)."""
    if "promulgation_no" not in rec:
        return _general_sentence(eff_date), None
    checked = f"{snap['generated_date']} 확인" if snap.get("generated_date") else "배포 전 확인"
    head = (
        f"국가법령정보 조문별 변경 이력({checked})상 조회된 판본까지 이 조문의 최근 변경 기록은 {rec['law_kind']} "
        f"제{rec['promulgation_no']}호({rec['promulgation_date']} 공포)"
    )
    tail = f" effective_date({eff_date})는 조회된 법령 판본 전체의 시행일입니다."
    staged = rec.get("staged_dates")
    if staged:
        # v0.63.0: 조항 조회·조립 실패는 시행일 목록을 잃는 일반 문장이 아니라 v0.60.0 분리 시행 문장으로.
        try:
            key = f"{rec['promulgation_no']}|{rec['promulgation_date']}"
            clause = (law.get("clauses") or {}).get(key)
            if clause:
                return _staged_clause_sentence(head, staged, clause, tail), key
        except Exception:  # noqa: BLE001
            pass
        return _staged_sentence(head, staged, tail), None
    return (
        f"{head}이고, 그 판본은 {rec['version_effective_date']}에 시행되었습니다. 그 부칙에서 조문별 "
        f"시행일을 따로 정했다면 그에 따릅니다.{tail}"
    ), None


def _para_list(nos: list[int]) -> str:
    return "·".join(f"제{n}항" for n in nos)


def _group_subject(items: list) -> str:
    """그룹 안 항별 라벨 → "제1항·제2항의 개정 표지와 제3항의 삭제 표지". 삭제 항은 맨 뒤(현재 효력 항과 구분)."""
    order: list[str] = []
    by_label: dict[str, list[int]] = {}
    for n, label in sorted(items, key=lambda it: (it[1] == "삭제", it[0])):
        if label not in by_label:
            order.append(label)
            by_label[label] = []
        by_label[label].append(n)
    parts = [f"{_para_list(by_label[label])}의 {label} 표지" for label in order]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + "와 " + parts[-1]


def _group_line(g: dict, clauses: dict, shown: set, state: dict, with_clause: bool) -> str:
    """그룹 1개의 문장. state["guided"]는 조항 판단 안내를 이미 실었는지(블록 전체에서 한 번만)."""
    items = g["items"]
    other = "(타법개정)" if g.get("amendment_kind") == "타법개정" else ""
    subject = f"{_group_subject(items)}({g['promulgation_date']} 공포)는 {g['law_kind']} 제{g['promulgation_no']}호{other}와 대응"
    deleted = [n for n, label in items if label == "삭제"]
    del_sent = f" {_para_list(deleted)}은 이 개정으로 삭제되었습니다." if deleted else ""
    staged = g.get("staged_dates")
    if not staged:
        return (f"{subject}하고, 그 판본은 {g['version_effective_date']}에 시행되었습니다.{del_sent} "
                "그 부칙에서 조문별 시행일을 따로 정했다면 그에 따릅니다.")
    which = "이 항에" if len(items) == 1 else "각 항에"
    line = (f"{subject}합니다. 그 판본의 시행일은 {'·'.join(staged)}로 나뉘어 있어 {which} 어느 날짜가 해당하는지 "
            f"이 응답으로 정하지 않습니다.{del_sent}")
    if not with_clause:
        return line
    key = f"{g['promulgation_no']}|{g['promulgation_date']}"
    clause = clauses.get(key)
    if not clause:
        return line
    if key in shown:
        line += " 그 개정의 부칙 시행일 조항 원문은 위에 실은 것과 같습니다."
    else:
        shown.add(key)
        line += (f" 그 개정의 부칙 시행일 조항 원문은 다음과 같습니다.\n{clause}\n"
                 "이 원문은 그 개정으로 바뀐 부분의 시행일을 정합니다.")
    if state.get("guided"):
        line += " 판단 방법은 위 안내와 같습니다."
    else:
        state["guided"] = True
        line += " " + _CLAUSE_GUIDANCE
    return line


def _assemble_block(rec: dict, groups: list, clauses: dict, base_key: str | None, with_clause: bool,
                    all_groups: list | None = None) -> str:
    """groups = 실을 그룹(길이 축약 뒤일 수 있음). 레코드 부재 문장은 축약 전 전체 그룹(all_groups)으로 판단한다 —
    레코드의 그룹이 길이 제한으로 빠졌을 뿐인데 "표지가 항 본문에 없다"고 말하지 않게(Redteam diff Codex MAJOR)."""
    shown = {base_key} if base_key else set()
    state = {"guided": base_key is not None}  # 조문 단위 문장에 조항을 실었으면 안내도 이미 실렸다
    lines = [_PARA_HEAD]
    full = groups if all_groups is None else all_groups
    if "promulgation_no" in rec and not any(int(g["promulgation_no"]) == int(rec["promulgation_no"]) for g in full):
        lines.append(f"이 조문의 최근 변경 기록({rec['law_kind']} 제{rec['promulgation_no']}호)의 표지는 항 본문에 없어 "
                     "어느 항이 바뀌었는지 이 응답으로 알 수 없습니다.")
    for g in groups:
        lines.append(_group_line(g, clauses, shown, state, with_clause))
    return "\n".join(lines)


def _paragraph_block(rec: dict, law: dict, base_key: str | None) -> str:
    """항별 블록(머리 + 레코드 부재 문장 + 그룹 문장). 1,500자 상한: 조항 원문부터 빼고, 그래도 넘으면 공포일이
    오래된 그룹부터 빼며 생략 문장을 단다. 그룹이 하나도 남지 않으면 빈 문자열."""
    groups = rec.get("paragraphs") or []
    if not groups:
        return ""
    clauses = law.get("clauses") or {}
    block = _assemble_block(rec, groups, clauses, base_key, with_clause=True)
    if len(block) <= _PARA_BLOCK_MAX_CHARS:
        return block
    block = _assemble_block(rec, groups, clauses, base_key, with_clause=False)
    if len(block) <= _PARA_BLOCK_MAX_CHARS:
        return block
    kept = list(groups)
    while len(kept) > 1:
        earliest = min(kept, key=lambda g: (g["promulgation_date"], int(g["promulgation_no"])))
        kept.remove(earliest)
        block = (_assemble_block(rec, kept, clauses, base_key, with_clause=False, all_groups=groups)
                 + "\n" + _PARA_OMITTED)
        if len(block) <= _PARA_BLOCK_MAX_CHARS:
            return block
    return ""


def notice_from_snapshot(snap: dict, rule_set_id: str, unit_id: str, served_doc_id: str, served_effective_raw: str,
                         stage_basis: str, eff_date: str, with_paragraphs: bool = True) -> str:
    """스냅샷 1개로 조립한 안내 문장(생성기의 크기 단계 전수 확인도 이 함수를 쓴다). 예외는 호출부가 막는다."""
    if stage_basis != "eflaw":
        return _general_sentence(eff_date)
    law = snap["laws"].get(rule_set_id)
    if law is None:
        return _general_sentence(eff_date)
    raw = (served_effective_raw or "").strip().replace("-", "")
    served_iso = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}" if len(raw) == 8 and raw.isdigit() else ""
    if law["mst"] != (served_doc_id or "").strip() or law["efyd"] != served_iso:
        _log_mismatch(rule_set_id)
        return _general_sentence(eff_date)
    rec = law["articles"].get(unit_id)
    if rec is None:
        return _general_sentence(eff_date)
    base, base_key = _base_sentence(snap, law, rec, eff_date)
    if not with_paragraphs:
        return base
    try:
        block = _paragraph_block(rec, law, base_key)
    except Exception:  # noqa: BLE001 — 항별 블록 실패는 기존 문장만 남긴다
        return base
    return f"{base}\n{block}" if block else base


def article_effective_notice(rule_set_id: str, unit_id: str, served_doc_id: str, served_effective_raw: str,
                             stage_basis: str, eff_date: str) -> str:
    """law 조문 상세의 article_effective_notice — never-raise(실패 시 일반 문장).

    조문별 문장은 stage_basis == "eflaw"이고 스냅샷의 mst·efyd가 서빙 판본과 같을 때만 쓴다.
    v0.66.0: 항별 그룹이 있으면 그 문장 뒤에 줄바꿈으로 항별 블록을 덧붙인다(블록 실패 시 기존 문장만).
    """
    try:
        return notice_from_snapshot(load_snapshot(), rule_set_id, unit_id, served_doc_id, served_effective_raw,
                                    stage_basis, eff_date)
    except Exception:  # noqa: BLE001 — 안내 조립 실패가 본문 응답을 막지 않게
        return _general_sentence(eff_date)
