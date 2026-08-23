"""v0.53.1 — NAS 라이브 이미지 의존성 lock 가드(Dockerfile + requirements.lock · 「법령 시행 단계 정합 시리즈」 lock 선행 릴리스).

무엇을 잠그는가(비프로그래머용): NAS 라이브 이미지를 만드는 Dockerfile이 ① 기반 이미지를 digest(지문)로 고정하고
② 제3자 의존성을 requirements.lock(라이브 실측 71종·정확 버전)에서만 설치하며 ③ 앱은 --no-deps로 설치한 뒤 pip check로
검증하고 ④ Dockerfile 본문에는 개별 핀(`이름==버전`)이 하나도 없는지(핀 증식 금지 규율)를 검사한다. lock 파일 자체도
"전 행이 정확 버전·중복 0·범위/URL/editable/extras/marker 없음·행 수 71"을 잠근다. 누군가 실수로 digest를 지우거나,
lock 밖에서 설치하거나, 핀을 Dockerfile에 다시 넣거나, lock에 범위 지정을 섞으면 이 테스트가 먼저 실패한다.

★이 테스트는 Dockerfile·requirements.lock·pyproject 텍스트만 읽는다(네트워크 0·docker 불요·추가 의존성 0).
lock이 실제 라이브와 같은지(71/71 전수 대조)·pip check 통과·기반 digest/Python/OpenSSL 일치는 배포 게이트(NAS 후보 이미지)가
별도로 확인한다. v0.53.0의 핀 6종(EXPECTED_PINS)은 lock 안에 같은 버전으로 포함돼야 한다(역사적 불변식 유지).
"""
import re
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# v0.53.1 기준값(라이브 실측 2026-08-23). 값을 바꾸려면 requirements.lock·Dockerfile·CHANGELOG·배포 게이트를 함께 갱신한다.
EXPECTED_LOCK_COUNT = 71
EXPECTED_BASE_IMAGE = "python:3.13-slim@sha256:b04b5d7233d2ad9c379e22ea8927cd1378cd15c60d4ef876c065b25ea8fb3bf3"
EXPECTED_PINS = {  # v0.53.0까지 Dockerfile에 직접 박혀 있던 핀 6종 — lock에 같은 버전으로 흡수됐는지 잠금
    "fastmcp": "3.4.2",
    "uvicorn": "0.48.0",
    "python-multipart": "0.0.30",
    "requests": "2.34.2",
    "urllib3": "2.7.0",
    "cyclopts": "4.23.1",
}
EXPECTED_DIRECT_DEPS = 6  # pyproject [project].dependencies 개수 — 새 직접 의존성이 검사에서 빠지지 않게 고정

_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][0-9A-Za-z.+!-]*)$")
_SPEC_RE = re.compile(r"^(>=|<=|==|>|<|~=|!=)\s*([0-9][0-9A-Za-z.]*)$")


def _norm(name: str) -> str:
    """PEP 503 정규화(대소문자·'_'/'.'→'-')."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _vtuple(v: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", v))


# ----------------------------------------------------------------------------- requirements.lock
def parse_lock_text(text: str) -> dict[str, str]:
    """lock 본문 → {정규화 이름: 정확 버전}. 주석·빈 줄만 허용, 그 외 행은 `이름==버전` 정확 핀이어야 한다.

    거부: 범위 지정(>=,~= 등)·`===`·와일드카드(`1.*`)·복수 specifier(`,`)·extras(`[x]`)·marker(`;`)·URL/VCS(`@`,`://`)·
    editable(`-e`)·옵션 행(`-r`,`--index-url`)·정규화 후 중복.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _PIN_RE.match(line)
        assert m, f"requirements.lock 행이 정확 핀(`이름==버전`)이 아님: {line!r}"
        assert "*" not in m.group(2), f"와일드카드 버전 금지: {line!r}"
        name = _norm(m.group(1))
        assert name not in out, f"requirements.lock 중복(정규화 후): {name}"
        out[name] = m.group(2)
    return out


def _lock() -> dict[str, str]:
    return parse_lock_text((ROOT / "requirements.lock").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- Dockerfile
def _dockerfile_text() -> str:
    return (ROOT / "Dockerfile").read_text(encoding="utf-8")


def _dockerfile_instructions(text: str) -> list[str]:
    """Dockerfile의 논리적 명령 목록(줄 연속 `\\` 병합·주석 줄 제외·앞뒤 공백 제거)."""
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
        if buf.strip():
            logical.append(buf.strip())
        buf = ""
    return logical


_INSTALLER_RE = re.compile(r"(?i)^(pip3?|python3?(\s+-m\s+pip)?|uv(\s+pip)?|poetry|pipx|conda)\b")
_ALLOWED_INSTALL_OPTS = {"--no-cache-dir", "--no-deps"}  # 결과 집합을 바꾸는 옵션(--constraint·--index-url·--pre 등)은 전부 금지


def _run_bodies(text: str) -> list[str]:
    """RUN 명령 본문 목록. exec-form(JSON)·heredoc(<<)·`;`·`||`·줄바꿈 연결은 가드가 해석할 수 없으므로 금지한다(redteam Codex MAJOR)."""
    bodies = []
    for ins in _dockerfile_instructions(text):
        if not re.match(r"(?i)^run\s", ins):
            continue
        body = re.sub(r"(?i)^run\s+", "", ins)
        assert not body.lstrip().startswith("["), f"RUN exec-form 금지(가드 해석 불가): {ins}"
        assert "<<" not in body, f"RUN heredoc 금지(가드 해석 불가): {ins}"
        assert ";" not in body and "||" not in body and "\n" not in body, f"RUN 안의 `;`·`||`·줄바꿈 금지(오류 억제·우회 차단): {ins}"
        bodies.append(body)
    return bodies


def _run_shell_commands(text: str) -> list[str]:
    """RUN 명령을 `&&` 단위의 개별 셸 명령으로 분해(그 외 연결자는 _run_bodies가 거부)."""
    cmds: list[str] = []
    for body in _run_bodies(text):
        cmds.extend(c.strip() for c in body.split("&&") if c.strip())
    return cmds


def _installer_commands(text: str) -> list[list[str]]:
    """설치기 호출(pip·pip3·python -m pip·uv·poetry·pipx·conda — 대소문자 무관) 전부를 토큰 목록으로 반환."""
    return [shlex.split(c) for c in _run_shell_commands(text) if _INSTALLER_RE.match(c)]


# ----------------------------------------------------------------------------- pyproject
def _pyproject_specs() -> dict[str, list[tuple[str, str]]]:
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
        n = max(len(v), len(b))
        vv, bb = v + (0,) * (n - len(v)), b + (0,) * (n - len(b))  # 길이 다른 튜플은 0 패딩(2 == 2.0.0)
        ok = {
            ">=": vv >= bb, "<=": vv <= bb, ">": vv > bb, "<": vv < bb,
            "==": vv == bb, "!=": vv != bb,
            "~=": vv >= bb and vv[: len(b) - 1] == bb[: len(b) - 1],
        }[op]
        if not ok:
            return False
    return True


# ============================================================================= tests
def test_lock_is_exact_pins_only_and_has_expected_count_v0531():
    """requirements.lock = 정확 핀 71행·중복 0(파서가 범위/URL/extras/marker/editable 행을 거부)."""
    lock = _lock()
    assert len(lock) == EXPECTED_LOCK_COUNT, f"lock 행 수 {len(lock)} ≠ 기대 {EXPECTED_LOCK_COUNT} (갱신 시 상수·CHANGELOG 동반)"


def test_lock_contains_legacy_pins_at_same_versions_v0531():
    """v0.53.0 핀 6종이 lock에 같은 버전으로 들어 있다(핀이 Dockerfile에서 사라졌을 뿐 조합은 그대로)."""
    lock = _lock()
    got = {k: lock.get(k) for k in EXPECTED_PINS}
    assert got == EXPECTED_PINS, f"핀 6종 불일치: {got} (기대 {EXPECTED_PINS})"


def test_lock_satisfies_pyproject_direct_dependency_ranges_v0531():
    """pyproject 직접 의존성 6종이 전부 lock에 있고 선언 범위를 만족한다(범위 밖이면 pip check가 빌드를 깨뜨림)."""
    lock, specs = _lock(), _pyproject_specs()
    assert len(specs) == EXPECTED_DIRECT_DEPS, f"직접 의존성 개수 {len(specs)} ≠ {EXPECTED_DIRECT_DEPS} — 상수·lock 동반 갱신"
    for name, clauses in specs.items():
        assert name in lock, f"직접 의존성 {name}이 requirements.lock에 없음"
        assert _satisfies(lock[name], clauses), f"{name}=={lock[name]}가 pyproject 범위 {clauses} 밖"


def test_dockerfile_base_image_pinned_by_digest_v0531():
    """FROM은 정확히 1개이고 기대 digest로 고정돼 있다(태그만 쓰면 재빌드 때 Python·OpenSSL·pip가 움직인다)."""
    froms = [i for i in _dockerfile_instructions(_dockerfile_text()) if re.match(r"(?i)^from\s", i)]
    assert len(froms) == 1, f"FROM은 1개여야 한다(발견 {len(froms)})"
    assert froms[0].split()[1] == EXPECTED_BASE_IMAGE, f"기반 이미지 불일치: {froms[0]!r}"


def test_dockerfile_installs_only_from_lock_then_app_no_deps_with_pip_check_v0531():
    """설치기 호출은 정확히 3개 = `pip install -r requirements.lock` → `pip install --no-deps .` → `pip check`.
    그 외 설치기(pip3·python -m pip·uv…)·추가 옵션(--constraint·--index-url…)·개별 핀·`;`/`||`/heredoc/exec-form 전부 금지.
    명령 전체 순서 = COPY requirements.lock < RUN lock 설치 < COPY src/ < RUN 앱 설치(+pip check)."""
    text = _dockerfile_text()
    calls = _installer_commands(text)
    assert [c[:2] for c in calls] == [["pip", "install"], ["pip", "install"], ["pip", "check"]], f"설치기 호출 불일치: {calls}"
    lock_install, app_install, check = calls
    assert lock_install[2:] == ["--no-cache-dir", "-r", "requirements.lock"], f"1단 lock 설치 인자 불일치: {lock_install}"
    assert app_install[2:] == ["--no-cache-dir", "--no-deps", "."], f"2단 앱 설치 인자 불일치: {app_install}"
    assert check == ["pip", "check"], f"pip check에 인자·억제 금지: {check}"
    for call in (lock_install, app_install):
        for tok in call[2:]:
            assert "==" not in tok and not _PIN_RE.match(tok), f"Dockerfile 개별 핀 금지(핀은 lock에만): {tok}"
            assert tok in _ALLOWED_INSTALL_OPTS or tok in ("-r", "requirements.lock", "."), f"허용 외 설치 인자: {tok}"
    # 같은 RUN 안에서 앱 설치 직후 pip check(앞선 명령 실패 시 && 단락으로 빌드 실패 = fail-closed)
    bodies = _run_bodies(text)
    app_body = next(b for b in bodies if "--no-deps" in b)
    parts = [c.strip() for c in app_body.split("&&")]
    assert parts[-1] == "pip check" and "--no-deps" in parts[-2], f"앱 설치 직후 `pip check`가 같은 RUN에 없다: {app_body}"
    # 명령 전체 순서
    ins = _dockerfile_instructions(text)
    def _idx(pattern):
        return next(i for i, x in enumerate(ins) if re.match(pattern, x))
    order = [_idx(r"(?i)^copy\s+requirements\.lock\b"), _idx(r"(?i)^run\s.*-r requirements\.lock"),
             _idx(r"(?i)^copy\s+src/"), _idx(r"(?i)^run\s.*--no-deps")]
    assert order == sorted(order), f"Dockerfile 순서 위반(lock COPY→lock 설치→src COPY→앱 설치): {order}"
    # 명령 본문(주석 제외) 전체에 `이름==버전` 토큰 0
    for x in ins:
        for tok in shlex.split(re.sub(r"(?i)^\w+\s+", "", x)) if not x.lstrip().startswith("[") else []:
            assert not _PIN_RE.match(tok), f"Dockerfile 명령에 개별 핀 토큰: {tok} ← {x}"


def test_lock_parser_rejects_non_exact_forms_selfcheck():
    """파서 부정 테스트(비-trivial 로직 자가 점검): 범위·===·와일드카드·복수 specifier·extras·marker·URL·editable·중복 거부."""
    import pytest

    assert parse_lock_text("# c\n\nFoo_Bar==1.0\nbaz==2.1.3\n") == {"foo-bar": "1.0", "baz": "2.1.3"}
    for bad in ("foo>=1.0", "foo===1.0", "foo==1.*", "foo==1.0,<2", "foo[extra]==1.0", "foo==1.0; python_version<'4'",
                "foo @ https://x/y.whl", "-e .", "-r other.txt", "git+https://x/y.git", "foo==1.0\nFOO==1.0"):
        with pytest.raises(AssertionError):
            parse_lock_text(bad)
    assert _satisfies("2.34.2", [(">=", "2"), ("<", "3")]) and not _satisfies("2.34.2", [(">=", "2.99"), ("<", "30")])
    assert _satisfies("2.0.0", [(">=", "2")]) and not _satisfies("1.9.9", [(">=", "2")])


def test_dockerfile_guard_rejects_bypass_forms_selfcheck():
    """가드 우회 부정 테스트(redteam Codex·Gemini): pip3/python -m pip/uv·`;`·`||`·heredoc·exec-form·추가 옵션이 잡히는지."""
    import pytest

    base = _dockerfile_text()
    assert len(_installer_commands(base)) == 3
    for bad in ("RUN python -m pip install foo==1.0", "RUN pip3 install bar", "RUN uv pip install baz", "RUN PIP install x"):
        assert _installer_commands(base + "\n" + bad + "\n"), f"설치기 우회 미검출: {bad}"
    for bad in ("RUN pip check || true", "RUN true; pip install x", "RUN [\"pip\", \"install\", \"x\"]", "RUN pip install -r <<EOF\nx\nEOF"):
        with pytest.raises(AssertionError):
            _run_bodies(base + "\n" + bad + "\n")
