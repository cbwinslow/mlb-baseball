"""`alert()` runs the user's hook without a shell and never lets the hook's own
failure escape (job-reliability spec: a failing hook leaves the job's exit code
unchanged)."""

import sys

from mlb_baseball import alert as alert_module


def _hook(tmp_path, monkeypatch, body: str) -> None:
    script = tmp_path / "hook.py"
    script.write_text(body)
    monkeypatch.setenv("MLB_ALERT_COMMAND", f"{sys.executable} {script}")


def test_unset_hook_only_logs(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("MLB_ALERT_COMMAND", raising=False)
    monkeypatch.delenv("MLB_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)  # no mlb.toml here
    assert alert_module.alert("boom") is False
    assert "ALERT: boom" in caplog.text


def test_hook_gets_message_on_stdin_and_as_last_argument(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    _hook(
        tmp_path,
        monkeypatch,
        f"import sys\nopen({str(out)!r}, 'w').write(sys.argv[-1] + '|' + sys.stdin.read())\n",
    )

    assert alert_module.alert("conform failed") is True
    assert out.read_text() == "conform failed|conform failed"


def test_failing_hook_is_swallowed(tmp_path, monkeypatch):
    _hook(tmp_path, monkeypatch, "import sys\nsys.exit(7)\n")
    assert alert_module.alert("x") is False


def test_missing_hook_program_is_swallowed(monkeypatch):
    monkeypatch.setenv("MLB_ALERT_COMMAND", "/no/such/program --flag")
    assert alert_module.alert("x") is False
