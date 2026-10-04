"""One-line step timings for the nightly log (stable-ids-incremental-conform
tasks 1.1-1.3: find where the time goes before changing anything)."""

import functools
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def timed(kind: str, label: str) -> Iterator[None]:
    """Prints ``<kind> step <label>: <N>s`` when the block ends, even on error."""
    started = time.monotonic()
    try:
        yield
    finally:
        print(f"{kind} step {label}: {time.monotonic() - started:.0f}s", flush=True)


def timed_step(kind: str, label_arg: int | None = None) -> Callable[[Callable], Callable]:
    """Decorator form of ``timed``. The label is the function name, or the
    positional argument ``label_arg`` (for example a table name) when given."""

    def wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> Any:
            label = str(args[label_arg]) if label_arg is not None else fn.__name__.lstrip("_")
            with timed(kind, label):
                return fn(*args, **kwargs)

        return inner

    return wrap
