import importlib
import os
import sys
import textwrap

import pytest

from mlb_baseball.shard import run_sharded

WORKERS = textwrap.dedent(
    """
    import os

    def square_worker(shard, offset, *, report):
        for item in shard:
            report((item, item * item + offset, os.getpid()))

    def failing_worker(shard, *, report):
        raise ValueError("boom in child")

    def dying_worker(shard, *, report):
        os._exit(3)  # killed without reporting anything
    """
)


@pytest.fixture
def workers(tmp_path):
    """Workers must be importable by name in a spawned child, so they live in a real module
    on sys.path (spawn hands the parent's sys.path to the child)."""
    (tmp_path / "shard_test_workers.py").write_text(WORKERS)
    sys.path.insert(0, str(tmp_path))
    try:
        yield importlib.import_module("shard_test_workers")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("shard_test_workers", None)


def test_every_item_is_processed_once_across_processes(workers):
    seen = []
    run_sharded(
        list(range(20)), workers.square_worker, processes=3, args=(1,), on_result=seen.append
    )
    assert sorted(item for item, _, _ in seen) == list(range(20))
    assert all(value == item * item + 1 for item, value, _ in seen)
    assert len({pid for _, _, pid in seen}) == 3  # really ran in three separate processes
    assert os.getpid() not in {pid for _, _, pid in seen}


def test_one_process_runs_inline_in_the_caller(workers):
    seen = []
    run_sharded([1, 2, 3], workers.square_worker, processes=1, args=(0,), on_result=seen.append)
    assert {pid for _, _, pid in seen} == {os.getpid()}


def test_a_worker_exception_surfaces_with_the_childs_traceback(workers):
    with pytest.raises(RuntimeError, match="boom in child"):
        run_sharded([1, 2, 3, 4], workers.failing_worker, processes=2, on_result=lambda r: None)


def test_a_process_that_dies_without_reporting_is_an_error(workers):
    with pytest.raises(RuntimeError, match="died"):
        run_sharded([1, 2, 3, 4], workers.dying_worker, processes=2, on_result=lambda r: None)
