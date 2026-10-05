"""Run one piece of work across several processes.

Threads share one interpreter lock, so a job that spends real CPU time per item (decoding
a large JSON answer and rendering it as CSV) stops getting faster once one core is full no
matter how many threads it has. Measured on the Polymarket backfill (2026-10-05): the
single ``mlb`` process sat at 94% of one core while PostgreSQL and the network were idle
waiting for it. ``run_sharded`` deals the items round-robin to ``processes`` spawned
processes, each running the worker (which may itself use threads for the network waits),
and hands every result back to the parent, which owns progress reporting.

Processes are started with ``spawn`` so a child never inherits the parent's database
connections or HTTP sessions. ``worker`` must be a module-level function and the items,
extra arguments and results must be picklable.
"""

from __future__ import annotations

import multiprocessing
import queue
import traceback
from collections.abc import Callable, Sequence
from typing import Any


def _child(
    worker: Callable[..., None],
    shard: Sequence[Any],
    args: tuple,
    results: Any,
    index: int,
) -> None:
    try:
        worker(shard, *args, report=lambda result: results.put(("result", index, result)))
        results.put(("done", index, None))
    except BaseException:
        results.put(("error", index, traceback.format_exc()))


def run_sharded(
    items: Sequence[Any],
    worker: Callable[..., None],
    *,
    processes: int,
    on_result: Callable[[Any], None],
    args: tuple = (),
) -> None:
    """Call ``worker(shard, *args, report=...)`` on ``processes`` shards of ``items``.

    ``report(result)`` inside a worker delivers ``result`` to ``on_result`` in the parent.
    With one process (or one item) the worker runs inline in this process, so tests and
    small jobs need no spawning. Raises ``RuntimeError`` with the child's traceback if a
    worker raised or a process died without finishing."""
    if processes <= 1 or len(items) <= 1:
        worker(list(items), *args, report=on_result)
        return
    ctx = multiprocessing.get_context("spawn")
    results: Any = ctx.Queue()
    shards = [list(items[i::processes]) for i in range(min(processes, len(items)))]
    children = [
        ctx.Process(target=_child, args=(worker, shard, args, results, index), daemon=True)
        for index, shard in enumerate(shards)
    ]
    for child in children:
        child.start()
    pending = set(range(len(children)))
    failure: str | None = None
    try:
        while pending:
            try:
                kind, index, payload = results.get(timeout=5)
            except queue.Empty:
                dead = [i for i in pending if children[i].exitcode not in (None, 0)]
                if dead:
                    failure = (
                        f"worker process {dead[0]} died (exit code {children[dead[0]].exitcode})"
                    )
                    break
                continue
            if kind == "result":
                on_result(payload)
            elif kind == "done":
                pending.discard(index)
            else:
                failure = payload
                break
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
        for child in children:
            child.join()
    if failure:
        raise RuntimeError(f"sharded worker failed:\n{failure}")
