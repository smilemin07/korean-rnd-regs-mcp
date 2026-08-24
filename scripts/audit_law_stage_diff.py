"""law↔eflaw 시행 단계 정합 전수 감사 — 「법령 시행 단계 정합 시리즈」 P2(v0.54.0) 동반 도구(read-only).

무엇을 검사하는가(비프로그래머용): 서버가 법령 본문으로 쓰는 `lawService target=law&MST=X`는 "그 공포본의
개정규정을 시행 단계와 무관하게 전부 합친 텍스트"(공포 합본)입니다. 반면 오늘 실제로 시행 중인 본문은
`lawService target=eflaw&MST=X&efYd=<시행일자>`(시행일 기준 편집본)에서만 나옵니다. 두 본문이 다르면
서버가 (가) 이미 시행된 개정을 누락하거나 (나) 아직 시행되지 않은 개정을 현행처럼 보여주고 있는 것입니다.
본 스크립트는 law 대상 규정 전건(35건)에 대해 두 본문을 같은 방식으로 파싱·정규화해 조문·별표 단위로
전부 비교(full diff)하고, 시행 단계 표(`lawSearch target=eflaw` — 현행·연혁·시행예정 전 단계 행)를 함께
수집해 "같은 MST 다단계"·"시행예정 판본"·"manifest ID가 시행예정 행에만 존재" 같은 함정을 표시합니다.

판정(규정별):
  MATCH    : 서버가 서빙하는 MST의 law 본문 == 그 MST의 시행일 편집본(조문·별표 전부 일치).
  DIFF     : 상이 존재 → 항목별로 [law에만 있음]=미시행 신설 선노출 가능 / [eflaw에만 있음]=시행 완료분 누락 /
             [본문 상이]=같은 조문인데 내용이 다름. 사람 판정(known_limitations·eflaw 적용 대상 결정) 대상.
  UNKNOWN  : 조회·파싱 실패, 조문/별표 키 충돌, 현행 행 0건·복수 등으로 '차이 없음'을 증명할 수 없음
             (fail-closed 승격 — 승격 전 판정은 verdict_before_promotion. 재실행·사람 확인 대상).
  FORMAT_ONLY : 상이 부분에 글자·숫자가 없음(공백·괄호·기호뿐 = 실질 무변 — 편집본 렌더링 차이).
  플래그   : MULTI_STAGE_OPEN(서빙 MST에 아직 도래하지 않은 시행 단계가 있음 = 분리시행 공존 → "수동 판정 필요")
             MULTI_STAGE_DONE(서빙 MST가 다단계였으나 전 단계 도래 — 정보용)
             PENDING(시행예정 행 존재: MST@시행일자)  SERVED_NOT_CURRENT(서빙 MST가 eflaw 현행 행이 아님)
             ★예측 플래그(시행 단계 표만으로 본문 오차를 예측 — 2026-08-23 전수 감사에서 실측 diff와 4/4 일치·오탐 0):
             MISSING_PREDICTED  = 서빙 공포본보다 "나중에 공포"됐는데 이미 시행된 다른 공포본이 있음 → law 합본이 그
                                  개정을 담지 못함(시행 완료분 누락 예측. 예: 혁신법 283413↔283849 06-11분)
             PREMATURE_PREDICTED = 서빙 공포본보다 "먼저 공포"됐는데 아직 미시행 단계가 남은 공포본이 있음 → law 합본이
                                  그 미시행 개정을 이미 합쳐 보여줌(미시행 선노출 예측. 예: 시행령 288773↔288335 09-11·2027분).
                                  서빙 공포본 자체에 미도래 단계가 남은 경우(MULTI_STAGE_OPEN)도 같은 이유로 선노출 예측에 포함.
             ★예측은 경량 조기 경보(검색 행만·수 초)이며 full diff와 사람 대조를 대체하지 않는다(예측 부재 ≠ 정합 증명).
             SAME_DAY_AMBIGUOUS(서빙 공포본과 같은 날 공포된 다른 공포본 존재 — 날짜만으로 합본 기준 선후를 정할 수 없어 수동 판정)
             MANIFEST_FUTURE_ONLY(★FAIL — manifest ID가 시행예정 행에만 존재 = fallback이 미시행 본문 서빙)
             MANIFEST_CHANGED(manifest ID ≠ 현행 MST — /regs-audit의 CHANGED와 동일 의미)

종료 코드: 0 = 전건 MATCH·플래그 FAIL 없음 / 3 = MANIFEST_FUTURE_ONLY 또는 SERVED_NOT_CURRENT 존재 /
          2 = DIFF·FORMAT_ONLY·UNKNOWN·MULTI_STAGE_OPEN·SAME_DAY_AMBIGUOUS 존재(사람 판정 필요).
          DIFF는 "감사 발견"이지 게이트 실패가 아닙니다(알려진 DIFF와 신규 DIFF의 구분은 --json-out 결과를 기준선으로 사람이 대조).

사용(read-only — manifest·코드·라이브 서버를 건드리지 않음, 로컬에서 law.go.kr만 호출):
  /Users/andykim/my_project/venv/bin/python scripts/audit_law_stage_diff.py                 # law 35건 전체
  /Users/andykim/my_project/venv/bin/python scripts/audit_law_stage_diff.py innovation_act   # 지정만
  옵션: --json-out <path>(상세 JSON) --cache-dir <dir>(개발용 응답 캐시·검색 행은 링크 제외 JSON만 저장)

보안: 키(LAW_API_KEY/OC)는 어떤 형태로도 출력·저장하지 않는다. lawSearch 행의 `…링크` 필드(API가 OC 키를
원문 삽입)는 읽지도 저장하지도 않는다. 캐시에 쓰는 상세 XML은 키 문자열 부재를 확인한 뒤에만 저장한다.
"""
import argparse
import difflib
import html
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SAFE_ROW_FIELDS = ("법령ID", "법령일련번호", "법령명한글", "소관부처명", "시행일자", "공포일자", "공포번호",
                   "제개정구분명", "현행연혁코드", "자법타법여부")
_SEARCH_DISPLAY = 100


# --------------------------------------------------------------------------- 순수 함수(테스트 가능)
def norm_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def extract_body(root, build_article_content) -> dict:
    """law·eflaw 응답에 대칭 적용하는 추출기 — 서버 get_law_detail과 같은 필터(조문여부=조문)·같은 본문 조립."""
    articles: dict[str, dict] = {}
    for a in root.findall(".//조문단위"):
        if (a.findtext("조문여부") or "").strip() != "조문":
            continue
        no = (a.findtext("조문번호", "") or "").strip()
        branch = (a.findtext("조문가지번호", "") or "").strip()
        key = f"제{no}조" + (f"의{branch}" if branch else "")
        articles[key] = {
            "title": norm_text(a.findtext("조문제목", "")),
            "content": norm_text(build_article_content(a)),
        }
    annexes: dict[str, dict] = {}
    for ann in root.findall(".//별표단위"):
        no = (ann.findtext("별표번호", "") or "").strip()
        branch = (ann.findtext("별표가지번호", "") or "").strip()
        kind = (ann.findtext("별표구분", "") or "").strip()
        key = f"{kind or '별표'} {no}" + (f"의{branch}" if branch else "")
        annexes[key] = {
            "title": norm_text(html.unescape(ann.findtext("별표제목", "") or "")),
            "content": norm_text(ann.findtext("별표내용", "")),
        }
    basic = {t: norm_text(root.findtext(f".//{t}", "")) for t in ("법령ID", "법령명_한글", "시행일자", "공포일자", "공포번호", "제개정구분")}
    n_art = sum(1 for a in root.findall(".//조문단위") if (a.findtext("조문여부") or "").strip() == "조문")
    n_ann = len(root.findall(".//별표단위"))
    # 키 충돌 불변식(redteam Codex): 같은 (번호,가지)·(구분,번호,가지)가 둘이면 dict가 조용히 덮어쓴다 → 집계로 드러낸다
    return {"basic": basic, "articles": articles, "annexes": annexes,
            "key_collisions": {"articles": n_art - len(articles), "annexes": n_ann - len(annexes)}}


def first_difference(a: str, b: str, width: int = 70) -> tuple[str, str]:
    """두 문자열의 첫 상이 지점 앞뒤 발췌(사람 판정용)."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        lo_a, lo_b = max(0, i1 - width // 2), max(0, j1 - width // 2)
        return a[lo_a:i2 + width // 2][: width * 2], b[lo_b:j2 + width // 2][: width * 2]
    return "", ""


def diff_bodies(law: dict, eflaw: dict) -> dict:
    """law(공포 합본) vs eflaw(시행일 편집본) full diff — 조문·별표 각각 only_in_law / only_in_eflaw / changed."""
    out = {}
    for section in ("articles", "annexes"):
        l, e = law[section], eflaw[section]
        only_law = sorted(set(l) - set(e), key=_sort_key)
        only_eflaw = sorted(set(e) - set(l), key=_sort_key)
        changed = []
        for k in sorted(set(l) & set(e), key=_sort_key):
            if l[k]["title"] != e[k]["title"] or l[k]["content"] != e[k]["content"]:
                la, ea = first_difference(l[k]["content"], e[k]["content"]) if l[k]["content"] != e[k]["content"] \
                    else (l[k]["title"], e[k]["title"])
                # 형식 차이 = 상이 부분에 글자·숫자가 하나도 없음(공백·괄호·기호뿐 → 의미 변화 불가)
                ws_only = l[k]["title"] == e[k]["title"] and not re.search(r"[\w가-힣]", _delta_text(l[k]["content"], e[k]["content"]))
                changed.append({"key": k, "law_excerpt": la, "eflaw_excerpt": ea,
                                "title_changed": l[k]["title"] != e[k]["title"], "ws_only": ws_only,
                                "delta_chars": _delta_chars(l[k]["content"], e[k]["content"])})
        out[section] = {"only_in_law": only_law, "only_in_eflaw": only_eflaw, "changed": changed,
                        "law_count": len(l), "eflaw_count": len(e)}
    out["is_match"] = all(
        not out[s]["only_in_law"] and not out[s]["only_in_eflaw"] and not out[s]["changed"] for s in ("articles", "annexes")
    )
    out["is_format_only"] = (not out["is_match"]) and all(
        not out[s]["only_in_law"] and not out[s]["only_in_eflaw"] and all(c["ws_only"] for c in out[s]["changed"])
        for s in ("articles", "annexes")
    )
    return out


def _delta_text(a: str, b: str) -> str:
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return "".join(a[i1:i2] + b[j1:j2] for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def _delta_chars(a: str, b: str) -> int:
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum((i2 - i1) + (j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def _sort_key(k: str):
    nums = [int(x) for x in re.findall(r"\d+", k)]
    return (nums + [0, 0])[:2], k


def stage_flags(rows: list[dict], served_mst: str, manifest_mst: str, today: str = "99999999") -> dict:
    """시행 단계 표(eflaw 전 행)에서 플래그 도출 — 순수 함수(tests/test_audit_law_stage_diff.py)."""
    by_mst: dict[str, set] = {}
    current, future = [], []
    for r in rows:
        by_mst.setdefault(r["법령일련번호"], set()).add(r["시행일자"])
        code = r.get("현행연혁코드", "")
        if code == "현행":
            current.append(r)
        elif code == "시행예정":
            future.append(r)
    cur_msts = {r["법령일련번호"] for r in current}
    fut_msts = {r["법령일련번호"] for r in future}
    flags = []
    served_stages = sorted(by_mst.get(served_mst, ()))
    if len(served_stages) >= 2:
        flags.append("MULTI_STAGE_OPEN" if served_stages[-1] > today else "MULTI_STAGE_DONE")
    if future:
        flags.append("PENDING")
    # ★공포 순서 ↔ 시행 순서 역전 예측(law 합본 = 그 공포본 기준 통합 텍스트이므로, 서빙 공포본 이후에 공포된
    # 개정은 담지 못하고, 그 이전에 공포된 개정은 시행 전이라도 전부 합쳐 담는다)
    served_pub = ""
    for r in rows:
        if r["법령일련번호"] == served_mst and r.get("공포일자"):
            served_pub = r["공포일자"]
            break
    missing_pred, premature_pred, same_day = [], [], []
    if served_pub:
        for r in rows:
            if r["법령일련번호"] == served_mst:
                # 서빙 공포본 자체의 미도래 단계도 law 합본에 이미 합쳐져 있다(선노출) — redteam Codex·Claude 반영
                if r["시행일자"] > today:
                    premature_pred.append((r["법령일련번호"], r["시행일자"], r["공포일자"]))
                continue
            if r["공포일자"] == served_pub and r.get("공포번호", "") != "":
                same_day.append((r["법령일련번호"], r["시행일자"], r["공포일자"]))  # 날짜만으로 선후 판정 불가
            if r["시행일자"] <= today and r["공포일자"] > served_pub:
                missing_pred.append((r["법령일련번호"], r["시행일자"], r["공포일자"]))
            if r["시행일자"] > today and r["공포일자"] < served_pub:
                premature_pred.append((r["법령일련번호"], r["시행일자"], r["공포일자"]))
    if missing_pred:
        flags.append("MISSING_PREDICTED")
    if premature_pred:
        flags.append("PREMATURE_PREDICTED")
    if same_day:
        flags.append("SAME_DAY_AMBIGUOUS")
    if served_mst not in cur_msts:
        flags.append("SERVED_NOT_CURRENT")
    if manifest_mst in fut_msts and manifest_mst not in cur_msts:
        flags.append("MANIFEST_FUTURE_ONLY")
    elif manifest_mst not in cur_msts:
        flags.append("MANIFEST_CHANGED")
    cur_date = ""
    dates = sorted({r["시행일자"] for r in current if r["법령일련번호"] == served_mst})
    if len(dates) == 1:
        cur_date = dates[0]
    return {
        "flags": flags,
        "current_rows": [(r["법령일련번호"], r["시행일자"]) for r in current],
        "future_rows": sorted((r["법령일련번호"], r["시행일자"]) for r in future),
        "served_stages": served_stages,
        "served_promulgation_date": served_pub,
        "missing_predicted": sorted(missing_pred),
        "premature_predicted": sorted(premature_pred),
        "same_day_ambiguous": sorted(same_day),
        "efyd": cur_date,
        "current_count": len(current),
    }


# --------------------------------------------------------------------------- LIVE 수집
class Collector:
    def __init__(self, client, cache_dir: Path | None):
        self.client = client
        self.cache_dir = cache_dir
        self.calls = 0
        self.elapsed = 0.0
        from korean_rnd_regs_mcp.live_api import _build_article_content, _parse_xml, _request_with_retry
        self._build = _build_article_content
        self._parse = _parse_xml
        self._get = _request_with_retry

    def _cached(self, name: str):
        if not self.cache_dir:
            return None
        p = self.cache_dir / name
        return p.read_bytes() if p.exists() else None

    def _store(self, name: str, data: bytes) -> None:
        if not self.cache_dir:
            return
        key = (self.client.api_key or "").encode("utf-8")
        if key and key in data:
            return  # 키가 섞인 응답은 절대 디스크에 남기지 않는다(fail-closed)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / name).write_bytes(data)

    def _fetch_xml(self, endpoint: str, params: dict, cache_name: str):
        import xml.etree.ElementTree as ET
        raw = self._cached(cache_name)
        if raw is None:
            t0 = time.perf_counter()
            resp = self._get(f"{self.client.base_url}/{endpoint}", {"OC": self.client.api_key, "type": "XML", **params})
            self.elapsed += time.perf_counter() - t0
            self.calls += 1
            root = self._parse(resp)
            self._store(cache_name, resp.content)
            return root
        return ET.fromstring(raw)

    def stage_rows(self, title: str, ministry: str | None) -> list[dict]:
        """lawSearch target=eflaw(전 단계 행) — 제목 정확일치·부처 정확일치 행만. 링크 필드는 읽지 않는다."""
        cache_name = f"search_eflaw_{re.sub(r'[^0-9A-Za-z가-힣]', '_', title)}.json"
        cached = self._cached(cache_name)
        if cached is not None:
            return json.loads(cached.decode("utf-8"))
        c = self.client
        norm = c._normalize_title(title)
        rows, page, seen = [], 1, 0
        while True:
            t0 = time.perf_counter()
            resp = self._get(f"{c.base_url}/lawSearch.do", {
                "OC": c.api_key, "type": "XML", "target": "eflaw", "query": title,
                "display": _SEARCH_DISPLAY, "page": page,
            })
            self.elapsed += time.perf_counter() - t0
            self.calls += 1
            root = self._parse(resp)
            total = int(root.findtext(".//totalCnt", "0") or "0")
            items = root.findall(".//law")
            for e in items:
                if c._normalize_title(e.findtext("법령명한글", "") or "") != norm:
                    continue
                if not c._ministry_matches(ministry or "", e.findtext("소관부처명", "") or ""):
                    continue
                rows.append({t: norm_text(e.findtext(t, "")) for t in SAFE_ROW_FIELDS})
            seen += len(items)
            if not items or seen >= total or page >= 20:
                break
            page += 1
        self._store(cache_name, json.dumps(rows, ensure_ascii=False).encode("utf-8"))
        return rows

    def body(self, target: str, mst: str, efyd: str = "") -> dict:
        params = {"target": target, "MST": mst}
        if efyd:
            params["efYd"] = efyd
        root = self._fetch_xml("lawService.do", params, f"{target}_{mst}_{efyd or 'x'}.xml")
        out = extract_body(root, self._build)
        # ★fail-open 차단(v0.54.0 diff 적대검토 Codex MAJOR 1): 종전 조건은 "조문 0건 AND 법령명 0"이라
        # 기본정보만 돌아온 응답(파싱 shape 변경·부분 오류 페이지)이 통과했고, 양쪽이 그렇게 되면 빈 dict끼리
        # 비교돼 MATCH로 오판했다(빈 fixture로 재현됨). 대상 35건은 전부 법률·시행령·시행규칙이라 조문 0건은
        # 정상 상태가 아니므로, 조문이 없으면 즉시 실패시켜 audit_one이 UNKNOWN으로 승격하게 한다.
        if not out["articles"]:
            raise RuntimeError("empty_articles")
        if not out["basic"]["법령명_한글"]:
            raise RuntimeError("empty_basic")
        # provenance: eflaw는 요청한 기준일(efYd)의 편집본이어야 한다. 응답 시행일자가 다르면 우리가 비교한
        # 본문이 우리가 의도한 시행 단계가 아니므로 비교 자체가 무효다(조용한 오판보다 UNKNOWN이 낫다).
        if efyd and out["basic"]["시행일자"].replace("-", "") != efyd:
            raise RuntimeError(f"efyd_provenance_mismatch:{out['basic']['시행일자']}")
        return out


def audit_one(col: Collector, rs) -> dict:
    from korean_rnd_regs_mcp.live_api import LawApiError

    rec = {"id": rs.id, "title": rs.title, "manifest_mst": rs.api_doc_id, "manifest_effective_date": rs.effective_date,
           "verdict": "UNKNOWN", "flags": [], "errors": []}
    try:
        r = col.client.resolve_latest_doc_id(rs.title, "law", rs.api_doc_id, rs.ministry)
        rec["served_mst"] = r.doc_id
        rec["resolver"] = {"effective_date": r.effective_date, "is_updated": r.is_updated, "resolve_failed": r.resolve_failed,
                           "pending": (r.pending_doc_id, r.pending_effective_date) if r.pending_doc_id else None}
    except LawApiError as e:
        rec["served_mst"] = rs.api_doc_id
        rec["errors"].append(f"resolve:{e.code}")
    try:
        rows = col.stage_rows(rs.title, rs.ministry)
    except Exception as e:  # noqa: BLE001
        rows = []
        rec["errors"].append(f"stage_rows:{type(e).__name__}")
    st = stage_flags(rows, rec["served_mst"], rs.api_doc_id, col.client._today_kst())
    rec.update({k: st[k] for k in ("flags", "current_rows", "future_rows", "served_stages", "served_promulgation_date",
                                   "missing_predicted", "premature_predicted", "current_count")})
    efyd = st["efyd"]
    if not efyd:
        # 현행 행이 없거나 복수 → resolver 행 시행일자로 대체 시도(있으면), 없으면 UNKNOWN
        rd = (rec.get("resolver") or {}).get("effective_date", "").replace("-", "")
        efyd = rd if len(rd) == 8 else ""
        if not efyd:
            rec["errors"].append("efyd_undetermined")
            _promote_unknown(rec)
            return rec
    rec["efyd"] = efyd
    try:
        law = col.body("law", rec["served_mst"])
        ef = col.body("eflaw", rec["served_mst"], efyd)
    except Exception as e:  # noqa: BLE001
        rec["errors"].append(f"body:{type(e).__name__}")
        _promote_unknown(rec)
        return rec
    rec["law_basic"], rec["eflaw_basic"] = law["basic"], ef["basic"]
    rec["key_collisions"] = {"law": law["key_collisions"], "eflaw": ef["key_collisions"]}
    if any(v for side in rec["key_collisions"].values() for v in side.values()):
        rec["errors"].append("key_collision")
    rec["diff"] = diff_bodies(law, ef)
    rec["verdict"] = "MATCH" if rec["diff"]["is_match"] else ("FORMAT_ONLY" if rec["diff"]["is_format_only"] else "DIFF")
    if rs.api_doc_id != rec["served_mst"]:
        # fallback 경로 점검: resolve가 실패하면 manifest ID의 law 본문이 서빙된다. 그 본문을 "현재 시행 중인
        # 본문"(= 서빙 MST의 efYd 편집본)과 대조해, 폴백이 발동했을 때 사용자가 볼 오차를 미리 드러낸다.
        # (manifest MST 자신의 시행본과의 대조가 아니다 — 알고 싶은 것은 '지금 시행 중인 것과 얼마나 다른가'다.)
        try:
            fb = col.body("law", rs.api_doc_id)
            rec["fallback_diff"] = diff_bodies(fb, ef)
        except Exception as e:  # noqa: BLE001
            rec["errors"].append(f"fallback_body:{type(e).__name__}")
    _promote_unknown(rec)
    return rec


def _promote_unknown(rec: dict) -> None:
    """fail-closed 승격 — 수집·파싱 오류, 조문/별표 키 충돌, 현행 행 0건·복수는 '일치 증명'이 될 수 없다.

    (v0.54.0 구현 diff 적대검토 반영) 이런 상태에서 MATCH를 그대로 두면 "차이 없음"으로 읽혀,
    실제로는 비교되지 않은 규정이 정합한 것처럼 기준선에 박힌다. 판정을 UNKNOWN으로 올리고
    승격 전 판정은 verdict_before_promotion에 남겨 보고서에서 원인을 볼 수 있게 한다.
    """
    if rec.get("current_count") != 1:
        rec["errors"].append(f"current_rows_ambiguous:{rec.get('current_count')}")
    if rec["errors"] and rec["verdict"] != "UNKNOWN":
        rec["verdict_before_promotion"] = rec["verdict"]
        rec["verdict"] = "UNKNOWN"


def render(rec: dict) -> str:
    d = rec.get("diff")
    parts = [f"{rec['verdict']:7} | {rec['id']:30} | manifest {rec['manifest_mst']} → 서빙 {rec.get('served_mst', '?')}"
             f" | efYd {rec.get('efyd', '-')} | 단계 {','.join(rec.get('served_stages', [])) or '-'}"
             f" | 플래그 {','.join(rec['flags']) or '-'}"]
    if rec.get("future_rows"):
        parts.append(f"          시행예정: " + ", ".join(f"{m}@{dt}" for m, dt in rec["future_rows"]))
    if rec.get("missing_predicted"):
        parts.append("          누락 예측(서빙본 이후 공포·이미 시행): " + ", ".join(f"{m}@{dt}(공포 {pub})" for m, dt, pub in rec["missing_predicted"]))
    if rec.get("premature_predicted"):
        parts.append("          선노출 예측(서빙본 이전 공포·미시행 단계): " + ", ".join(f"{m}@{dt}(공포 {pub})" for m, dt, pub in rec["premature_predicted"]))
    if d:
        for sec, label in (("articles", "조문"), ("annexes", "별표")):
            s = d[sec]
            if s["only_in_law"] or s["only_in_eflaw"] or s["changed"]:
                parts.append(f"          {label} law {s['law_count']} / eflaw {s['eflaw_count']}"
                             f" · law에만 {s['only_in_law'] or '-'} · eflaw에만 {s['only_in_eflaw'] or '-'}"
                             f" · 본문 상이 {[c['key'] + ('(형식만)' if c['ws_only'] else f'({c[chr(100)+chr(101)+chr(108)+chr(116)+chr(97)+chr(95)+chr(99)+chr(104)+chr(97)+chr(114)+chr(115)]}자)') for c in s['changed']] or '-'}")
    if rec.get("fallback_diff") and not rec["fallback_diff"]["is_match"]:
        fd = rec["fallback_diff"]["articles"]
        parts.append(f"          fallback(manifest {rec['manifest_mst']}) vs 시행본: law에만 {fd['only_in_law'] or '-'}"
                     f" · eflaw에만 {fd['only_in_eflaw'] or '-'} · 상이 {[c['key'] for c in fd['changed']] or '-'}")
    if rec.get("verdict_before_promotion"):
        parts.append(f"          ※ 승격: {rec['verdict_before_promotion']} → UNKNOWN (아래 오류 사유)")
    if rec["errors"]:
        parts.append(f"          오류: {', '.join(rec['errors'])}")
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--json-out")
    ap.add_argument("--cache-dir")
    args = ap.parse_args(argv)

    load_dotenv(ROOT / ".env")
    if not bool(os.environ.get("LAW_API_KEY")):
        print("LAW_API_KEY 미설정 — .env를 확인하십시오 (값은 출력하지 않습니다).")
        return 2
    sys.path.insert(0, str(ROOT / "src"))
    from korean_rnd_regs_mcp.live_api import LawApiClient
    from korean_rnd_regs_mcp.manifest import Retrieval, load_manifest

    only = set(args.ids)
    items = [rs for rs in load_manifest() if rs.retrieval == Retrieval.LIVE_API and rs.api_target.value == "law"]
    unknown = only - {rs.id for rs in items}
    if unknown:
        print(f"지정 rule_set_id 미인식(law 대상만 가능): {', '.join(sorted(unknown))} (fail-closed).")
        return 2
    targets = [rs for rs in items if not only or rs.id in only]
    if not targets:
        print("감사 대상 0건 (fail-closed).")
        return 2

    client = LawApiClient()
    col = Collector(client, Path(args.cache_dir) if args.cache_dir else None)
    today = client._today_kst()
    print(f"기준일(오늘·KST): {today} · 대상 {len(targets)}건(law) · 모드 {'CACHE 재생 가능' if col.cache_dir else 'LIVE'}")
    records = []
    for rs in targets:
        rec = audit_one(col, rs)
        records.append(rec)
        print(render(rec), flush=True)
    counts = {v: sum(1 for r in records if r["verdict"] == v) for v in ("MATCH", "FORMAT_ONLY", "DIFF", "UNKNOWN")}
    fail = [r["id"] for r in records if {"MANIFEST_FUTURE_ONLY", "SERVED_NOT_CURRENT"} & set(r["flags"])]
    multi = [r["id"] for r in records if "MULTI_STAGE_OPEN" in r["flags"]]
    pending = [r["id"] for r in records if "PENDING" in r["flags"]]
    predicted = {r["id"] for r in records if {"MISSING_PREDICTED", "PREMATURE_PREDICTED"} & set(r["flags"])}
    actual = {r["id"] for r in records if r["verdict"] == "DIFF"}
    print(f"요약: MATCH {counts['MATCH']} / FORMAT_ONLY {counts['FORMAT_ONLY']} / DIFF {counts['DIFF']} / UNKNOWN {counts['UNKNOWN']}"
          f" (전체 {len(records)}) · MULTI_STAGE_OPEN {len(multi)} · PENDING {len(pending)} · FAIL 플래그 {len(fail)}"
          f" · 예측↔실측 DIFF 일치 {len(predicted & actual)}/{len(predicted | actual)}"
          f"{'' if predicted == actual else ' ★불일치: ' + ', '.join(sorted(predicted ^ actual))}"
          f" · LIVE 호출 {col.calls}회 {col.elapsed:.1f}s")
    if args.json_out:
        from datetime import datetime, timedelta, timezone
        meta = {"today": today, "run_at_kst": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S"),
                "mode": "LIVE" if col.calls else "CACHE_REPLAY", "live_calls": col.calls,
                "cache_dir": str(col.cache_dir) if col.cache_dir else None, "targets": len(records)}
        Path(args.json_out).write_text(json.dumps({"meta": meta, "records": records}, ensure_ascii=False, indent=1), encoding="utf-8")
    if fail:
        print(f"→ FAIL 플래그: {', '.join(fail)} — manifest/서빙 ID가 현행 행이 아님(사람 판정 NO-GO).")
        return 3
    ambiguous = [r["id"] for r in records if "SAME_DAY_AMBIGUOUS" in r["flags"]]
    if counts["DIFF"] or counts["FORMAT_ONLY"] or counts["UNKNOWN"] or multi or ambiguous:
        print("→ DIFF·FORMAT_ONLY·UNKNOWN·MULTI_STAGE_OPEN·SAME_DAY_AMBIGUOUS 존재: 사람 판정 필요"
              "(known_limitations·eflaw 적용 대상 결정 — FORMAT_ONLY도 자동 통과가 아니라 눈으로 1회 확인).")
        return 2
    print("→ 전건 MATCH.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
