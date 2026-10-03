"""`mlb runs` / `mlb runs --check` through the real argparse in `cli.main`, with
the one database query faked (the SQL is covered in tests/integration)."""

from datetime import UTC, datetime, timedelta

import pytest

from mlb_baseball import alert, cli, runs

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _run(source="retrosheet", mode="update", status="success", ago_h=2.0, **kw):
    started = NOW - timedelta(hours=ago_h)
    return runs.JobRun(
        source=source,
        mode=mode,
        status=status,
        attempt=kw.get("attempt", 1),
        started_at=started,
        finished_at=started + timedelta(minutes=5),
        error=kw.get("error"),
        success_at=kw.get("success_at", started + timedelta(minutes=5)),
    )


@pytest.fixture
def fake(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(alert, "alert", lambda message: sent.append(message) or True)

    def install(rows):
        monkeypatch.setattr(runs, "fetch_runs", lambda: rows)
        return sent

    return install


def test_healthy_jobs_exit_zero_and_send_nothing(fake, capsys):
    sent = fake([_run(), _run(source="conform", mode="nightly", ago_h=5)])
    with pytest.raises(SystemExit) as exc:
        cli.main(["runs", "--check"])
    assert exc.value.code == 0
    assert sent == []
    out = capsys.readouterr().out
    assert "retrosheet:update" in out and "conform:nightly" in out


def test_failed_last_run_exits_one_and_alerts_once(fake):
    sent = fake([_run(status="failed", error="boom", success_at=NOW - timedelta(hours=30))])
    with pytest.raises(SystemExit) as exc:
        cli.main(["runs", "--check"])
    assert exc.value.code == 1
    assert len(sent) == 1 and "retrosheet:update" in sent[0] and "boom" in sent[0]


def test_stale_job_is_listed_and_fails_the_check(fake, capsys):
    sent = fake([_run(ago_h=40), _run(source="mlb_api", ago_h=0.5)])
    with pytest.raises(SystemExit) as exc:
        cli.main(["runs", "--check"])
    assert exc.value.code == 1
    # mlb_api has a 15-minute limit, so 30 minutes old is stale; daily ones get 28 h.
    assert "retrosheet:update" in sent[0] and "mlb_api:update" in sent[0]
    assert "STALE" in capsys.readouterr().out


def test_without_check_a_bad_job_is_shown_but_exit_is_zero(fake, capsys):
    sent = fake([_run(ago_h=40)])
    with pytest.raises(SystemExit) as exc:
        cli.main(["runs"])
    assert exc.value.code == 0
    assert sent == []
    assert "STALE" in capsys.readouterr().out


def test_running_job_with_a_recent_success_is_healthy():
    running = _run(status="running")
    assert running.problem(NOW) is None
