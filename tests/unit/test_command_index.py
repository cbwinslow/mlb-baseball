"""docs/COMMANDS.md is generated from the argparse tree; it fails when stale."""

from pathlib import Path

from mlb_baseball import command_index


def test_command_index_is_current():
    expected = command_index.build()
    actual = Path("docs/COMMANDS.md").read_text()
    assert actual == expected, "run: python -m mlb_baseball.command_index > docs/COMMANDS.md"


def test_every_declared_upkeep_command_exists_in_the_cli():
    parser = command_index._parser()
    import argparse

    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert set(command_index.EFFECTS) <= set(sub.choices)


def test_every_write_command_declares_its_effect():
    assert all(v for v in command_index.EFFECTS.values()), (
        "each upkeep command needs a stated effect"
    )
