"""조문별 변경 이력 스냅샷 로더·안내 문장 조립 (v0.60.0, law 조문 상세 전용).

데이터는 배포 전 `scripts/extract_article_history.py`가 만든 `article_history.json`뿐이다 — 런타임
네트워크 호출은 없다. 로드는 첫 사용 때 1회(lazy)이며, 파일 누락·손상은 빈 스냅샷으로 대체하고
WARNING 1회만 남긴다(본문 응답 무영향). 레코드 하나가 형식에 맞지 않으면 그 레코드만 버린다.

스냅샷은 생성 시점의 서빙 판본(mst·efyd)에 묶인다. 호출부는 서빙 판본이 같을 때만 조문별 문장을
쓰고, 다르면 일반 문장으로 내려간다 — 낡은 스냅샷이 다른 판본의 날짜를 단정하지 않게 한다.
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

_lock = threading.Lock()
_snapshot: dict | None = None

# 스냅샷 불일치 INFO 로그 — 규정별 시간당 1회(키 = rule_set_id, 항목 수는 규정 수 수준).
_MISMATCH_LOG_INTERVAL_S = 3600.0
_mismatch_last: dict[str, float] = {}
_mismatch_lock = threading.Lock()


def _valid_date(s: object) -> bool:
    if not isinstance(s, str) or not _ISO_DATE.match(s):
        return False
    try:
        time.strptime(s, "%Y-%m-%d")
    except ValueError:
        return False
    return True


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


def _load_uncached(path: Path) -> dict:
    """파일 → {"generated_date": str, "laws": {rule_set_id: {"mst","efyd","articles"}}}. 실패 시 빈 스냅샷."""
    empty = {"generated_date": "", "laws": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema") != _SCHEMA_VERSION or not isinstance(raw.get("laws"), dict):
            logger.warning("article_history: 스냅샷 형식 이상 — 조문별 변경 이력 안내 없이 동작")
            return empty
        gen = raw.get("generated_at")
        gen_date = gen[:10] if isinstance(gen, str) and _valid_date(gen[:10]) else ""
        laws: dict = {}
        for rid, law in raw["laws"].items():
            if not (isinstance(rid, str) and isinstance(law, dict)):
                continue
            mst, efyd, arts = law.get("mst"), law.get("efyd"), law.get("articles")
            if not (isinstance(mst, str) and mst.isascii() and mst.isdigit() and _valid_date(efyd) and isinstance(arts, dict)):
                continue
            clean = {}
            for jo, rec in arts.items():
                if isinstance(jo, str) and _JO_KEY.match(jo):
                    c = _clean_article(rec)
                    if c is not None:
                        clean[jo] = c
            laws[rid] = {"mst": mst, "efyd": efyd, "articles": clean}
        return {"generated_date": gen_date, "laws": laws}
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
    return (
        f"effective_date({eff_date})는 조회된 법령 판본 전체의 시행일이며, 이 조문의 시행일과 같다는 뜻은 "
        "아닙니다. 조문별 시행일은 국가법령정보센터의 조문 연혁과 부칙에서 확인하십시오."
    )


def article_effective_notice(rule_set_id: str, unit_id: str, served_doc_id: str, served_effective_raw: str,
                             stage_basis: str, eff_date: str) -> str:
    """law 조문 상세의 article_effective_notice 1문장 — never-raise(실패 시 일반 문장).

    조문별 문장은 stage_basis == "eflaw"이고 스냅샷의 mst·efyd가 서빙 판본과 같을 때만 쓴다.
    """
    try:
        if stage_basis != "eflaw":
            return _general_sentence(eff_date)
        snap = load_snapshot()
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
        checked = f"{snap['generated_date']} 확인" if snap.get("generated_date") else "배포 전 확인"
        head = (
            f"국가법령정보 조문별 변경 이력({checked})상 조회된 판본까지 이 조문의 최근 변경 기록은 {rec['law_kind']} "
            f"제{rec['promulgation_no']}호({rec['promulgation_date']} 공포)"
        )
        tail = f" effective_date({eff_date})는 조회된 법령 판본 전체의 시행일입니다."
        staged = rec.get("staged_dates")
        if staged:
            return (
                f"{head}입니다. 그 판본의 시행일이 {'·'.join(staged)}로 나뉘어 있어, 이 조문의 시행일은 이 응답으로 "
                f"정할 수 없으니 그 부칙에서 확인하십시오.{tail}"
            )
        return (
            f"{head}이고, 그 판본은 {rec['version_effective_date']}에 시행되었습니다. 그 부칙에서 조문별 "
            f"시행일을 따로 정했다면 그에 따릅니다.{tail}"
        )
    except Exception:  # noqa: BLE001 — 안내 조립 실패가 본문 응답을 막지 않게
        return _general_sentence(eff_date)
