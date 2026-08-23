"""v0.53.0 — Dockerfile HTTP 클라이언트 의존성 핀 가드(「법령 시행 단계 정합 시리즈」 P1 / 코드리뷰 로드맵 단계 4).

무엇을 잠그는가(비프로그래머용): NAS 라이브 이미지를 만드는 Dockerfile의 `pip install` 명령에
고정 버전(핀)이 정확히 6종 — fastmcp·uvicorn·python-multipart·requests·urllib3·cyclopts — 라이브 실측값
(2026-08-23 v0.52.0 컨테이너)으로 박혀 있는지, 그리고 그 값이 pyproject.toml이 선언한 허용 범위
안에 있는지를 검사한다. 누군가 실수로 핀을 지우거나, 중복·추가 핀을 넣거나, pyproject 범위와
어긋나는 값으로 바꾸면 이 테스트가 먼저 실패한다.

★이 테스트는 Dockerfile·pyproject 텍스트만 읽는다(네트워크 0·docker 불요·추가 의존성 0).
실제 이미지의 pip freeze가 라이브와 일치하는지·`pip check`가 통과하는지는 배포 게이트(NAS 후보
이미지)가 별도로 확인한다. urllib3는 requests의 전이 의존성이라 pyproject에 없으므로 범위 검사
대상이 아니며, 호환성은 후보 이미지 resolver·`pip check`가 증명한다(diff 적대검토 Codex 반영).
cyclopts는 배포 게이트의 pip freeze 전수 대조에서 유일하게 드리프트한 패키지(라이브 4.23.1·후보 4.23.2)를
라이브값으로 동결한 것 — fastmcp CLI 전용이라 서버 런타임 import 0건(python -v 실측)이며 pyproject에도 없다.
"""
import re
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# v0.53.0 기준 핀(라이브 실측값). 값을 바꾸려면 Dockerfile·본 상수·CHANGELOG를 함께 갱신한다.
EXPECTED_PINS = {
    "fastmcp": "3.4.2",
    "uvicorn": "0.48.0",
    "python-multipart": "0.0.30",
    "requests": "2.34.2",
    "urllib3": "2.7.0",
    "cyclopts": "4.23.1",
}

_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][0-9A-Za-z.]*)$")
_SPEC_RE = re.compile(r"^(>=|<=|==|>|<|~=|!=)\s*([0-9][0-9A-Za-z.]*)$")


def _norm(name: str) -> str:
    """PEP 503 정규화(대소문자·'_'/'.'→'-')."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _vtuple(v: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", v))


def _dockerfile_run_commands() -> list[str]:
    """Dockerfile의 논리적 RUN 명령 목록(줄 연속 `\\` 병합·주석 줄 제외)."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    logical: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if not buf and line.lstrip().startswith("#"):
            continue
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        logical.append(buf.strip())
        buf = ""
    return [ln for ln in logical if re.match(r"(?i)^run\s", ln)]


def _dockerfile_pins() -> dict[str, str]:
    """`pip install` RUN 명령 1개에서 `이름==버전` 토큰을 전부 추출(중복은 오류)."""
    installs = [ln for ln in _dockerfile_run_commands() if re.search(r"\bpip\s+install\b", ln)]
    assert len(installs) == 1, f"Dockerfile의 `pip install` RUN 명령은 정확히 1개여야 한다(발견 {len(installs)})"
    tokens = shlex.split(re.sub(r"(?i)^run\s+", "", installs[0]))
    pins: dict[str, str] = {}
    for tok in tokens:
        m = _PIN_RE.match(tok)
        if not m:
            continue
        name = _norm(m.group(1))
        assert name not in pins, f"Dockerfile 핀 중복: {name}"
        pins[name] = m.group(2)
    return pins


def _pyproject_specs() -> dict[str, list[tuple[str, str]]]:
    """pyproject.toml [project].dependencies → {정규화 이름: [(op, version), ...]}."""
    import tomllib

    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    out: dict[str, list[tuple[str, str]]] = {}
    for spec in deps:
        m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$", spec)
        assert m, f"pyproject 의존성 파싱 실패: {spec!r}"
        clauses = []
        for part in filter(None, (p.strip() for p in m.group(2).split(","))):
            sm = _SPEC_RE.match(part)
            assert sm, f"pyproject specifier 파싱 실패: {spec!r} ← {part!r}"
            clauses.append((sm.group(1), sm.group(2)))
        out[_norm(m.group(1))] = clauses
    return out


def _satisfies(version: str, clauses: list[tuple[str, str]]) -> bool:
    v = _vtuple(version)
    for op, bound in clauses:
        b = _vtuple(bound)
        # 길이가 다른 튜플 비교는 0 패딩(2 == 2.0.0)
        n = max(len(v), len(b))
        vv, bb = v + (0,) * (n - len(v)), b + (0,) * (n - len(b))
        ok = {
            ">=": vv >= bb, "<=": vv <= bb, ">": vv > bb, "<": vv < bb,
            "==": vv == bb, "!=": vv != bb,
            "~=": vv >= bb and vv[: len(b) - 1] == bb[: len(b) - 1],
        }[op]
        if not ok:
            return False
    return True


def test_dockerfile_pins_exactly_expected_v0530():
    """핀 집합이 기대 6종과 정확히 같다(누락·추가·중복·값 불일치 전부 실패)."""
    pins = _dockerfile_pins()
    assert pins == EXPECTED_PINS, f"Dockerfile 핀 불일치: {pins} (기대 {EXPECTED_PINS})"


def test_dockerfile_pins_within_pyproject_ranges_v0530():
    """Dockerfile에서 실제로 추출한 핀 값이 pyproject.toml 선언 범위를 만족한다(범위 밖이면 pip 충돌로 빌드 실패).
    pyproject에 선언된 패키지(fastmcp·requests)만 검사 — uvicorn·python-multipart·urllib3·cyclopts는 전이 의존성."""
    pins = _dockerfile_pins()
    specs = _pyproject_specs()
    checked = 0
    for name, ver in pins.items():
        if name in specs:
            assert _satisfies(ver, specs[name]), f"{name}=={ver}가 pyproject 범위 {specs[name]} 밖"
            checked += 1
    assert checked == 2, f"pyproject 선언 패키지 중 핀된 것은 fastmcp·requests 2종이어야 한다(검사 {checked})"


def test_satisfies_helper_selfcheck():
    """버전 비교 헬퍼 자체 점검(비-trivial 로직의 최소 자가 검증)."""
    assert _satisfies("2.34.2", [(">=", "2"), ("<", "3")])
    assert not _satisfies("2.34.2", [(">=", "2.99"), ("<", "30")])
    assert _satisfies("3.4.2", [(">=", "3.3"), ("<", "4")])
    assert not _satisfies("3.2.9", [(">=", "3.3"), ("<", "4")])
    assert _satisfies("2.0.0", [(">=", "2")]) and not _satisfies("1.9.9", [(">=", "2")])
