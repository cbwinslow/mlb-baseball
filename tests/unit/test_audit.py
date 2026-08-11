from mlb_baseball import audit


def test_sample_limits_and_omits_empty_values():
    assert audit._sample([]) == ""
    assert audit._sample([1, 2, 3, 4, 5, 6]) == "; sample: 1, 2, 3, 4, 5"


def test_print_report_summarizes_statuses(monkeypatch, capsys):
    monkeypatch.setattr(
        audit,
        "run",
        lambda _scope: [
            audit.Finding("pass", "PASS", "fine"),
            audit.Finding("warning", "WARN", "needs review"),
            audit.Finding("skipped", "SKIP", "not loaded"),
        ],
    )

    assert audit.print_report("game")
    output = capsys.readouterr().out
    assert "[PASS] pass: fine" in output
    assert "1/3 passed; 1 warnings; 0 failures; 1 skipped" in output


def test_print_report_returns_false_for_a_failure(monkeypatch):
    monkeypatch.setattr(
        audit,
        "run",
        lambda _scope: [audit.Finding("failed", "FAIL", "broken")],
    )

    assert not audit.print_report("game")
