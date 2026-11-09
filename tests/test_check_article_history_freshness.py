"""스냅샷 신선도 매일 확인 도구 — 비교·알림 규칙·키 마스킹·종료 코드(네트워크 0, 알림·git은 mock)."""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_article_history_freshness as chk  # noqa: E402

_SNAP = {"schema": 1, "generated_at": "2026-10-28 23:24 KST",
         "laws": {"a_act": {"mst": "100", "efyd": "2026-01-01", "articles": {}},
                  "b_act": {"mst": "200", "efyd": "2026-02-02", "articles": {}}}}


def test_parse_snapshot_and_date_normalization():
    gen, laws = chk.parse_snapshot(json.dumps(_SNAP))
    assert gen == "2026-10-28 23:24 KST" and laws == {"a_act": ("100", "20260101"), "b_act": ("200", "20260202")}
    with pytest.raises(ValueError):
        chk.parse_snapshot(json.dumps({"schema": 2, "laws": {}}))
    with pytest.raises(ValueError):
        chk.parse_snapshot(json.dumps({"schema": 1, "laws": {}}))


def test_compare_iso_and_8digit_dates_equal():
    base = {"a_act": ("100", "20260101"), "b_act": ("200", "20260202")}
    assert chk.compare(base, {"a_act": ("100", "2026-01-01"), "b_act": ("200", "20260202")}) == ([], [])
    changed, failed = chk.compare(base, {"a_act": ("101", "20261001"), "b_act": None})
    assert changed == [("a_act", "100", "20260101", "101", "20261001")] and failed == ["b_act"]
    assert chk.compare(base, {"a_act": ("100", "20260101")}) == ([], ["b_act"])  # 빠진 법령 = 실패


def test_decide_change_alert_rules():
    ch = [("a_act", "100", "20260101", "101", "20261001")]
    sig = json.dumps(ch, ensure_ascii=False)
    d = date(2026, 11, 2)
    assert chk.decide(ch, [], {}, d)[0] is True                                   # 첫 변경
    assert chk.decide(ch, [], {"alert_sig": sig, "alerted_on": "2026-11-01"}, d)[0] is False  # 같은 변경, 1일 뒤
    assert chk.decide(ch, [], {"alert_sig": sig, "alerted_on": "2026-10-26"}, d)[0] is True   # 7일 지남
    other = ch + [("b_act", "200", "20260202", "201", "20261101")]
    assert chk.decide(other, [], {"alert_sig": sig, "alerted_on": "2026-11-01"}, d)[0] is True  # 목록이 바뀜
    assert chk.decide(ch, [], {"alert_sig": sig, "alerted_on": "망가짐"}, d)[0] is True
    _, _, st = chk.decide([], [], {"alert_sig": sig, "alerted_on": "2026-11-01"}, d)
    assert st["alert_sig"] == "" and st["alerted_on"] is None                    # 해소되면 초기화


def test_decide_failure_needs_two_consecutive_runs_and_does_not_hide_change():
    ch = [("a_act", "100", "20260101", "101", "20261001")]
    nc, nf, st = chk.decide(ch, ["b_act"], {}, date(2026, 11, 2))
    assert nc is True and nf is False and st["fail_streak"] == 1                 # 첫 실패라도 변경은 알림
    nc, nf, st = chk.decide([], ["b_act"], st, date(2026, 11, 3))
    assert nf is True and st["fail_streak"] == 2
    assert chk.decide([], [], st, date(2026, 11, 4))[2]["fail_streak"] == 0      # 성공 실행이면 0


def test_mask_removes_key_and_oc_values():
    assert chk.mask("x SECRET9 y OC=abc&type=XML", "SECRET9") == "x *** y OC=***&type=XML"


def test_load_state_missing_and_corrupt(tmp_path):
    assert chk.load_state(tmp_path / "none.json") == ({}, False)
    p = tmp_path / "s.json"
    p.write_text("{망가짐", encoding="utf-8")
    assert chk.load_state(p) == ({}, True)


class _Res(SimpleNamespace):
    pass


class _Client:
    api_key = "SECRET-KEY-77"
    calls = 0

    def __init__(self, table=None, raise_for=()):
        self.table = table or {"A법": ("100", "2026-01-01"), "B법": ("200", "2026-02-02")}
        self.raise_for = set(raise_for)

    def resolve_latest_doc_id(self, title, target, doc_id, ministry):
        _Client.calls += 1
        if title in self.raise_for:
            raise RuntimeError(f"connection failed for https://x/DRF?OC={self.api_key}&target=law")
        doc, ef = self.table[title]
        return _Res(doc_id=doc, effective_date=ef, resolve_failed=False)


def _setup(tmp_path, monkeypatch, client, notified):
    import korean_rnd_regs_mcp.live_api as la
    import korean_rnd_regs_mcp.manifest as mf
    snap = tmp_path / "base.json"
    snap.write_text(json.dumps(_SNAP), encoding="utf-8")
    monkeypatch.setattr(chk, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(chk, "code_info", lambda: "test 0000000")
    monkeypatch.setattr(chk, "DONE_MARK_PATH", tmp_path / "done")       # 실제 상태 폴더에 쓰지 않게
    monkeypatch.setattr(chk, "now_kst", lambda: datetime(2026, 11, 10, 4, 0, tzinfo=chk.KST))
    monkeypatch.setattr(la, "LawApiClient", lambda: client)
    rs = [SimpleNamespace(id="a_act", title="A법", api_doc_id="1", ministry="x", api_target=SimpleNamespace(value="law")),
          SimpleNamespace(id="b_act", title="B법", api_doc_id="2", ministry="x", api_target=SimpleNamespace(value="law"))]
    monkeypatch.setattr(mf, "load_manifest", lambda *a, **k: rs)
    monkeypatch.setattr(chk, "notify", lambda t, m: notified.append(m) or True)
    return snap


def test_main_no_change_exit_0(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 0 and notified == []
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert st["last_success"] == st["last_run"]


def test_main_change_exit_1_and_alert_once(tmp_path, monkeypatch):
    notified = []
    c = _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")})
    snap = _setup(tmp_path, monkeypatch, c, notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 1
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 1
    assert notified == ["판본 변경 1건. 로그를 확인하십시오."]  # 같은 변경은 두 번째에 알리지 않음


def test_main_failed_notify_is_retried_next_run(tmp_path, monkeypatch):
    notified = []
    c = _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")})
    snap = _setup(tmp_path, monkeypatch, c, notified)
    monkeypatch.setattr(chk, "notify", lambda t, m: False)
    chk.main(["--notify", "--snapshot", str(snap)])
    monkeypatch.setattr(chk, "notify", lambda t, m: notified.append(m) or True)
    chk.main(["--notify", "--snapshot", str(snap)])
    assert notified == ["판본 변경 1건. 로그를 확인하십시오."]  # 알림 실패는 기록하지 않아 다음 실행에 다시 알림


def test_main_failure_exit_2_no_retry_and_no_key_in_output(tmp_path, monkeypatch, capsys):
    notified = []
    _Client.calls = 0
    snap = _setup(tmp_path, monkeypatch, _Client(raise_for={"B법"}), notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert _Client.calls == 2  # 법령마다 1회(재시도는 실패 캐시 때문에 무의미해 삭제)
    assert notified == []      # 실패 1회째는 알리지 않음
    assert "조회 실패: b_act (RuntimeError)" in capsys.readouterr().out
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["조회 실패 1건. 로그를 확인하십시오."]
    out = capsys.readouterr()
    assert "SECRET-KEY-77" not in out.out + out.err and "OC=" not in out.out + out.err


def test_main_top_level_exception_prints_type_only(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)

    def boom(*a, **k):
        raise RuntimeError("https://x/DRF?OC=SECRET-KEY-77")
    monkeypatch.setattr(chk, "compare", boom)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    out = capsys.readouterr()
    assert "오류: RuntimeError" in out.out and "SECRET-KEY-77" not in out.out + out.err
    assert notified == ["확인 중 오류가 났습니다. 로그를 확인하십시오."]


def test_main_manifest_mismatch_and_corrupt_state_alert_immediately(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    (tmp_path / "state.json").write_text("{망가짐", encoding="utf-8")
    data = json.loads(snap.read_text(encoding="utf-8"))
    data["laws"]["c_act"] = {"mst": "300", "efyd": "2026-03-03"}
    snap.write_text(json.dumps(data), encoding="utf-8")
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["조회 실패 1건 · 설정 오류 2건. 로그를 확인하십시오."]


def test_main_missing_key_exit_3(tmp_path, monkeypatch):
    notified = []
    c = _Client()
    c.api_key = ""
    snap = _setup(tmp_path, monkeypatch, c, notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 3 and len(notified) == 1


def test_main_missing_baseline_exit_2(tmp_path, monkeypatch):
    notified = []
    _setup(tmp_path, monkeypatch, _Client(), notified)
    assert chk.main(["--notify", "--snapshot", str(tmp_path / "nope.json")]) == 2 and len(notified) == 1


def test_record_deployed_rejects_option_like_ref():
    assert chk.record_deployed("--output=/tmp/x") == 2


def test_record_deployed_writes_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(chk, "BASELINE_PATH", tmp_path / "base.json")
    monkeypatch.setattr(chk, "DONE_MARK_PATH", tmp_path / "done")  # 실제 완료 표시를 지우지 않게
    assert chk.record_deployed("HEAD") == 0
    gen, laws = chk.parse_snapshot((tmp_path / "base.json").read_text(encoding="utf-8"))
    assert len(laws) >= 30


class _FailClient(_Client):
    """실제 resolver처럼 예외 대신 resolve_failed 결과를 돌려준다(사유 코드 포함)."""

    def __init__(self, codes):
        super().__init__()
        self.codes = codes

    def resolve_latest_doc_id(self, title, target, doc_id, ministry):
        if title in self.codes:
            _Client.calls += 1
            return _Res(doc_id=doc_id, effective_date="", resolve_failed=True, resolve_error_code=self.codes[title])
        return super().resolve_latest_doc_id(title, target, doc_id, ministry)


def test_resolve_failed_called_once_and_reason_printed(tmp_path, monkeypatch, capsys):
    notified = []
    _Client.calls = 0
    snap = _setup(tmp_path, monkeypatch, _FailClient({"B법": "zero_rows"}), notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert _Client.calls == 2
    assert "조회 실패: b_act (zero_rows)" in capsys.readouterr().out


def test_auth_failed_is_config_error_alerted_immediately(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _FailClient({"A법": "auth_failed", "B법": "auth_failed"}), notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["조회 실패 2건 · 설정 오류 1건. 로그를 확인하십시오."]


def test_empty_effective_date_is_failure_not_change(tmp_path, monkeypatch, capsys):
    notified = []
    c = _Client({"A법": ("999", ""), "B법": ("200", "20260202")})  # 일치 행이 모두 미래 → manifest ID·빈 시행일
    snap = _setup(tmp_path, monkeypatch, c, notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    out = capsys.readouterr().out
    assert "판본 변경" not in out and "조회 실패: a_act (no_effective_date, 999)" in out


def test_decide_keeps_alert_history_when_lookup_failed():
    ch = [("a_act", "100", "20260101", "101", "20261001")]
    st = {"alert_sig": json.dumps(ch, ensure_ascii=False), "alerted_on": "2026-11-01"}
    _, _, new = chk.decide([], ["a_act"], st, date(2026, 11, 2))
    assert new["alert_sig"] == st["alert_sig"] and new["alerted_on"] == "2026-11-01"
    assert chk.decide(ch, [], new, date(2026, 11, 3))[0] is False  # 회복 뒤 같은 변경을 다시 알리지 않음


@pytest.mark.parametrize("bad", ['{"fail_streak": "x"}', '{"fail_streak": true}', '{"fail_streak": -1}',
                                 '{"alert_sig": 3}', '{"alerted_on": 5}'])
def test_load_state_rejects_bad_field_types(tmp_path, bad):
    p = tmp_path / "s.json"
    p.write_text(bad, encoding="utf-8")
    assert chk.load_state(p) == ({}, True)


def test_header_printed_when_import_fails(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    monkeypatch.setitem(sys.modules, "dotenv", None)  # import 실패 흉내
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    out = capsys.readouterr().out
    assert "스냅샷 신선도 확인" in out and "오류: ModuleNotFoundError" in out and len(notified) == 1


def test_record_deployed_clears_done_mark(tmp_path, monkeypatch):
    monkeypatch.setattr(chk, "BASELINE_PATH", tmp_path / "base.json")
    mark = tmp_path / "done"
    mark.write_text("2026-11-10\n", encoding="utf-8")
    monkeypatch.setattr(chk, "DONE_MARK_PATH", mark)
    assert chk.record_deployed("HEAD") == 0 and not mark.exists()


def test_trouble_alert_once_per_day(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(raise_for={"B법"}), notified)
    for _ in range(3):                                   # 같은 날 04:00·08:40·로그인
        assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["조회 실패 1건. 로그를 확인하십시오."]   # 2회째에 1건, 3회째는 억제
    monkeypatch.setattr(chk, "now_kst", lambda: datetime(2026, 11, 11, 4, 0, tzinfo=chk.KST))
    chk.main(["--notify", "--snapshot", str(snap)])
    assert len(notified) == 2                            # 다음 날 다시 1건


def test_early_exit_trouble_alert_once_per_day(tmp_path, monkeypatch):
    notified = []
    _setup(tmp_path, monkeypatch, _Client(), notified)
    for _ in range(3):
        assert chk.main(["--notify", "--snapshot", str(tmp_path / "nope.json")]) == 2
    assert len(notified) == 1


def test_done_mark_written_only_on_full_success_after_4am(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    mark = tmp_path / "done"
    assert chk.main(["--snapshot", str(snap)]) == 0 and not mark.exists()          # --notify 없음(수동) → 안 씀
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 0
    assert mark.read_text(encoding="utf-8") == "2026-11-10\n"
    mark.unlink()
    monkeypatch.setattr(chk, "now_kst", lambda: datetime(2026, 11, 10, 1, 30, tzinfo=chk.KST))
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 0 and not mark.exists()  # 04:00 전


def test_done_mark_not_written_on_failure_or_failed_alert(tmp_path, monkeypatch):
    notified = []
    c = _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")})
    snap = _setup(tmp_path, monkeypatch, c, notified)
    monkeypatch.setattr(chk, "notify", lambda t, m: False)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 1 and not (tmp_path / "done").exists()
    monkeypatch.setattr(chk, "notify", lambda t, m: True)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 1 and (tmp_path / "done").exists()
    (tmp_path / "done").unlink()
    snap2 = _setup(tmp_path, monkeypatch, _Client(raise_for={"B법"}), notified)
    assert chk.main(["--notify", "--snapshot", str(snap2)]) == 2 and not (tmp_path / "done").exists()


def test_done_mark_not_written_when_baseline_replaced_mid_run(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    real_fetch = chk.fetch_current

    def fetch_and_redeploy(*a, **k):
        snap.write_text(snap.read_text(encoding="utf-8") + " ", encoding="utf-8")  # --record-deployed가 겹침
        return real_fetch(*a, **k)
    monkeypatch.setattr(chk, "fetch_current", fetch_and_redeploy)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 0
    assert not (tmp_path / "done").exists() and "기준 파일이 바뀌어" in capsys.readouterr().out


def test_decide_future_alerted_on_does_not_suppress_forever():
    ch = [("a_act", "100", "20260101", "101", "20261001")]
    st = {"alert_sig": json.dumps(ch, ensure_ascii=False), "alerted_on": "2099-01-01"}
    assert chk.decide(ch, [], st, date(2026, 11, 2))[0] is True


def test_non_digit_effective_date_is_failure(tmp_path, monkeypatch, capsys):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client({"A법": ("100", "-"), "B법": ("200", "20260202")}), notified)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert "조회 실패: a_act (no_effective_date, 100)" in capsys.readouterr().out



@pytest.mark.parametrize("raw", [b"\xff\xfe junk", b"[" * 200000])
def test_unreadable_state_is_corrupt_and_alerted(tmp_path, monkeypatch, raw):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)
    (tmp_path / "state.json").write_bytes(raw)
    assert chk.load_state(tmp_path / "state.json") == ({}, True)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["설정 오류 1건. 로그를 확인하십시오."]
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["trouble_alerted_on"] == "2026-11-10"


def test_lone_surrogate_and_unknown_keys_do_not_break_state_write(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")}), notified)
    (tmp_path / "state.json").write_text('{"alert_sig": "\\ud800", "junk": ' + "[" * 900 + "]" * 900 + "}", encoding="utf-8")
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 1
    st = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert "junk" not in st and notified == ["판본 변경 1건. 로그를 확인하십시오."]


def _fail_state_write(monkeypatch):
    real = chk.write_atomic

    def fake(path, text):
        if path == chk.STATE_PATH:
            raise OSError("disk full")
        return real(path, text)
    monkeypatch.setattr(chk, "write_atomic", fake)


def test_state_write_failure_after_trouble_alert_sends_one_alert(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(raise_for={"B법"}), notified)
    (tmp_path / "state.json").write_text(json.dumps({"fail_streak": 1}), encoding="utf-8")
    _fail_state_write(monkeypatch)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["조회 실패 1건. 로그를 확인하십시오."]


def test_state_write_failure_after_change_plus_first_failure_sends_one_alert(tmp_path, monkeypatch):
    notified = []
    c = _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")}, raise_for={"B법"})
    snap = _setup(tmp_path, monkeypatch, c, notified)
    _fail_state_write(monkeypatch)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["판본 변경 1건 · 조회 실패 1건. 로그를 확인하십시오."]


def test_state_write_failure_after_change_only_alert_is_still_reported(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client({"A법": ("101", "20261001"), "B법": ("200", "20260202")}), notified)
    _fail_state_write(monkeypatch)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["판본 변경 1건. 로그를 확인하십시오.", "상태 파일을 쓰지 못했습니다. 로그를 확인하십시오."]


def test_alert_still_sent_when_trouble_path_itself_fails(tmp_path, monkeypatch):
    notified = []
    snap = _setup(tmp_path, monkeypatch, _Client(), notified)

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(chk, "compare", boom)
    monkeypatch.setattr(chk, "notify_trouble", boom)
    assert chk.main(["--notify", "--snapshot", str(snap)]) == 2
    assert notified == ["확인 중 오류가 났습니다. 로그를 확인하십시오."]



def test_notify_trouble_does_not_overwrite_unreadable_state(tmp_path, monkeypatch):
    notified = []
    _setup(tmp_path, monkeypatch, _Client(), notified)
    (tmp_path / "state.json").write_bytes(b"\xff\xfe junk")
    chk.notify_trouble("x", "2026-11-10")
    assert notified == ["x"] and (tmp_path / "state.json").read_bytes() == b"\xff\xfe junk"
