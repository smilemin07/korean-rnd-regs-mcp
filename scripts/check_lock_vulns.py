"""requirements.lock의 의존성을 OSV 취약점 DB와 대조한다 — 주간 정기 확인 운영 도구(2026-10-28).

wheel에 포함되지 않는 운영자용 스크립트다(서버 실행과 무관). 표준 라이브러리만 쓴다.

사용 예(Mac 터미널):
  /Users/andykim/my_project/venv/bin/python scripts/check_lock_vulns.py
  /Users/andykim/my_project/venv/bin/python scripts/check_lock_vulns.py --notify   # 새 항목이 있으면 macOS 알림

동작:
  - requirements.lock의 `이름==버전` 행 전부를 OSV querybatch(https://api.osv.dev)로 한 번에 조회한다.
    보내는 것은 패키지 이름과 버전뿐이다.
  - 검토를 마친 공지는 lock_vuln_reviewed.json에 사유와 함께 적는다. 거기 없는 공지만 "새 항목"으로 보고한다.
  - 종료 코드: 0 = 새 항목 없음, 1 = 새 항목 있음, 2 = 조회·파일 오류(결과를 판단할 수 없음).
    조회 실패를 "새 항목 없음"으로 바꾸지 않는다(fail-closed).
  - --notify면 새 항목·오류가 있을 때 macOS 알림을 띄운다. 알림 문구에는 건수만 넣는다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements.lock"
REVIEWED = Path(__file__).resolve().parent / "lock_vuln_reviewed.json"
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)\s*$")
_TIMEOUT = 30


def parse_lock(text: str) -> list[tuple[str, str]]:
    """lock 본문에서 (이름, 버전) 목록을 읽는다. 주석·빈 줄은 건너뛰고, 그 밖의 형식은 오류로 본다."""
    pins = []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = _PIN.match(s)
        if not m:
            raise ValueError(f"requirements.lock {n}행을 해석할 수 없습니다")
        pins.append((m.group(1), m.group(2)))
    if not pins:
        raise ValueError("requirements.lock에 고정 버전 행이 없습니다")
    return pins


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.load(r)


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
        return json.load(r)


def query_osv(pins: list[tuple[str, str]], post=_post_json) -> dict[str, list[str]]:
    """{패키지==버전: [공지 ID, …]}를 돌려준다. 결과 수가 요청 수와 다르면 오류로 본다."""
    q = {"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in pins]}
    results = post(OSV_BATCH, q).get("results")
    if not isinstance(results, list) or len(results) != len(pins):
        raise ValueError("OSV 응답의 결과 수가 요청과 다릅니다")
    found = {}
    for (n, v), res in zip(pins, results):
        ids = [x["id"] for x in (res or {}).get("vulns", []) if isinstance(x, dict) and x.get("id")]
        if res and res.get("next_page_token"):
            raise ValueError(f"{n}=={v} 결과가 여러 쪽이라 일부만 받았습니다")
        if ids:
            found[f"{n}=={v}"] = ids
    return found


def describe(vid: str, get=_get_json) -> str:
    """공지 1건의 등급·요약·수정 버전을 한 줄로 만든다. 상세 조회가 실패해도 ID는 남긴다."""
    try:
        d = get(OSV_VULN + vid)
        sev = (d.get("database_specific") or {}).get("severity") or "등급 미상"
        fixed = sorted(
            {
                str(e["fixed"])
                for a in d.get("affected") or []
                for r in a.get("ranges") or []
                for e in r.get("events") or []
                if "fixed" in e
            }
        )
        summary = str(d.get("summary") or "").strip()[:120]
    except Exception:
        # 상세 형식이 어긋나도 새 항목 보고와 알림은 계속한다.
        return f"{vid} (상세 조회 실패)"
    return f"{vid} [{sev}] {summary} | 수정: {', '.join(fixed) or '없음'}"


def load_reviewed(path: Path = REVIEWED) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("reviewed"), dict):
        raise ValueError("lock_vuln_reviewed.json 형식이 맞지 않습니다")
    return data["reviewed"]


def new_findings(found: dict[str, list[str]], reviewed: dict) -> dict[str, list[str]]:
    out = {}
    for pkg, ids in found.items():
        fresh = [i for i in ids if i not in reviewed]
        if fresh:
            out[pkg] = fresh
    return out


def notify(title: str, message: str) -> None:
    # 문구는 내부에서 만든 건수 문장뿐이다. 따옴표만 걸러 AppleScript 문자열을 닫지 못하게 한다.
    safe = lambda s: s.replace("\\", "").replace('"', "")
    subprocess.run(
        ["osascript", "-e", f'display notification "{safe(message)}" with title "{safe(title)}"'],
        check=False,
        timeout=15,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="requirements.lock 취약점 정기 확인(OSV)")
    ap.add_argument("--notify", action="store_true", help="새 항목·오류가 있으면 macOS 알림")
    args = ap.parse_args(argv)
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    title = "korean-rnd-regs-mcp 취약점 확인"
    try:
        pins = parse_lock(LOCK.read_text(encoding="utf-8"))
        reviewed = load_reviewed()
        found = query_osv(pins)
    except Exception as e:
        print(f"[{stamp}] 오류: {e}")
        if args.notify:
            notify(title, "조회에 실패했습니다. 로그를 확인하십시오.")
        return 2
    fresh = new_findings(found, reviewed)
    total = sum(len(v) for v in found.values())
    print(f"[{stamp}] 패키지 {len(pins)}종 · 공지 {total}건(검토 완료 {total - sum(len(v) for v in fresh.values())}건)")
    if not fresh:
        print("새 항목 없음")
        return 0
    print("새 항목:")
    for pkg, ids in sorted(fresh.items()):
        for vid in ids:
            print(f"  {pkg}: {describe(vid)}")
    if args.notify:
        notify(title, f"새 공지 {sum(len(v) for v in fresh.values())}건. 로그를 확인하십시오.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
