"""acceptance spec 무결성 가드 — assert 종류 동결 + 구조 검증 (mock, 네트워크 0).

목적: run.py 해석기가 아는 assert 종류(5종)를 벗어난 spec이 슬그머니 늘어나, 비프로그래머가
유지보수 불가능해지는 것을 차단한다. 종류를 늘리려면 run.py·README·이 테스트를 함께 고쳐야 하는
'의도적 마찰'을 만든다. (LIVE 미호출 — spec/run 모듈을 import해 데이터 구조만 검사.)
"""
import importlib.util
from pathlib import Path

import pytest

_ACC_DIR = Path(__file__).resolve().parent / "acceptance"


def _load(path: Path):
    # spec_from_file_location: __name__ != "__main__" 이라 run.py의 main()은 실행되지 않음(부작용 0).
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_RUN = _load(_ACC_DIR / "run.py")
_SPECS = sorted(_ACC_DIR.glob("v*.py"))


def test_runner_frozen_assert_kinds():
    """assert 종류 동결 — 5종·block-eligible 2종 고정."""
    assert _RUN.ASSERT_KINDS == {
        "fetched_ok", "returned_not_below", "absent_error_code", "latency_under", "field_equals",
    }
    assert _RUN.BLOCK_ELIGIBLE == {"fetched_ok", "returned_not_below"}
    assert _RUN.BLOCK_ELIGIBLE <= _RUN.ASSERT_KINDS


def test_acceptance_dir_layout():
    assert _ACC_DIR.is_dir()
    assert (_ACC_DIR / "run.py").exists()
    assert (_ACC_DIR / "README.md").exists()
    assert _SPECS, "버전 spec(v*.py)이 최소 1개 있어야 함"


@pytest.mark.parametrize("spec_path", _SPECS, ids=lambda p: p.stem)
def test_spec_structure_and_frozen_kinds(spec_path):
    spec = _load(spec_path)
    checks = getattr(spec, "CHECKS", None)
    assert isinstance(checks, list) and checks, f"{spec_path.stem}.CHECKS 비어있음"
    for c in checks:
        assert {"name", "tool", "asserts"} <= set(c), f"{spec_path.stem}: check 필수 키 누락"
        assert isinstance(c["asserts"], list) and c["asserts"]
        for a in c["asserts"]:
            assert a.get("kind") in _RUN.ASSERT_KINDS, (
                f"{spec_path.stem}: 미허용 assert kind {a.get('kind')!r} "
                f"(허용 {sorted(_RUN.ASSERT_KINDS)})"
            )
    # block-eligible 신호가 최소 1개는 있어야 회귀 검출 의미가 있음
    kinds = {a.get("kind") for c in checks for a in c["asserts"]}
    assert kinds & _RUN.BLOCK_ELIGIBLE, f"{spec_path.stem}: 회귀 검출 신호(fetched_ok/returned_not_below) 최소 1개 필요"
    for p in getattr(spec, "LEVEL_B_PROMPTS", []):
        assert "probe_prompt" in p and "expect_behavior" in p
