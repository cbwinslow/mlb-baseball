from pathlib import Path

from scripts.check_dox import check_dox


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent(*, child: str | None = None) -> str:
    index = "No child DOX files."
    if child is not None:
        index = f"| Child | Scope |\n| --- | --- |\n| [{child}]({child}) | test child |"
    return f"# Test DOX\n\n## Purpose\n\nTest.\n\n## Child DOX Index\n\n{index}\n"


def _sidecar() -> str:
    return (
        "# source.py DOX\n\n"
        "## Purpose\n\nTest.\n\n"
        "## Ownership\n\nTest.\n\n"
        "## Verification\n\nTest.\n\n"
        "## Child DOX Index\n\nNo child DOX files.\n"
    )


def test_repository_dox_structure_is_valid() -> None:
    assert check_dox() == []


def test_check_dox_accepts_indexed_hierarchy_sidecar_and_claude_bridge(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", _agent(child="pkg/AGENTS.md"))
    _write(tmp_path / "CLAUDE.md", "@AGENTS.md\n")
    _write(tmp_path / "pkg" / "AGENTS.md", _agent())
    _write(tmp_path / "pkg" / "CLAUDE.md", "@AGENTS.md\n")
    _write(tmp_path / "pkg" / "source.py", "VALUE = 1\n")
    _write(tmp_path / "pkg" / "source.py.dox.md", _sidecar())

    assert check_dox(tmp_path, required_sidecars=()) == []


def test_check_dox_rejects_unindexed_child_agent(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", _agent())
    _write(tmp_path / "pkg" / "AGENTS.md", _agent())

    errors = check_dox(tmp_path, required_sidecars=())

    assert any("not listed in nearest parent index" in error for error in errors)


def test_check_dox_rejects_missing_index_target(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", _agent(child="missing/AGENTS.md"))

    errors = check_dox(tmp_path, required_sidecars=())

    assert any("Child DOX Index points to missing" in error for error in errors)


def test_check_dox_rejects_orphan_sidecar(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", _agent())
    _write(tmp_path / "missing.py.dox.md", _sidecar())

    errors = check_dox(tmp_path, required_sidecars=())

    assert any("orphan sidecar" in error for error in errors)


def test_check_dox_rejects_sidecar_missing_required_heading(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", _agent())
    _write(tmp_path / "source.py", "VALUE = 1\n")
    _write(
        tmp_path / "source.py.dox.md",
        "# source.py DOX\n\n## Purpose\n\nTest.\n\n## Child DOX Index\n\nNone.\n",
    )

    errors = check_dox(tmp_path, required_sidecars=())

    assert any("missing required heading '## Ownership'" in error for error in errors)
    assert any("missing required heading '## Verification'" in error for error in errors)


def test_check_dox_requires_adjacent_agents_import_in_claude_file(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", _agent(child="pkg/AGENTS.md"))
    _write(tmp_path / "pkg" / "AGENTS.md", _agent())
    _write(tmp_path / "pkg" / "CLAUDE.md", "# Claude-only rules\n")

    errors = check_dox(tmp_path, required_sidecars=())

    assert any("'@AGENTS.md' is not imported" in error for error in errors)


def test_check_dox_requires_explicit_baseline_sidecar(tmp_path: Path) -> None:
    _write(tmp_path / "AGENTS.md", _agent())

    errors = check_dox(tmp_path, required_sidecars=("pkg/required.py.dox.md",))

    assert any("required DOX sidecar is missing" in error for error in errors)
