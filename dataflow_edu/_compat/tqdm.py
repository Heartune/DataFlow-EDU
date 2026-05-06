"""Small fallback for tqdm when the optional progress dependency is absent."""

from __future__ import annotations

import sys
from typing import Any, Iterable, Iterator, TypeVar

T = TypeVar("T")

try:  # pragma: no cover - exercised when the real dependency is installed.
    from tqdm import tqdm as tqdm  # type: ignore
except Exception:  # pragma: no cover - fallback exists for slim/old deployments.

    class _FallbackTqdm:
        def __init__(
            self,
            iterable: Iterable[T] | None = None,
            total: int | None = None,
            desc: str | None = None,
            unit: str | None = None,
            initial: int = 0,
            **_: Any,
        ) -> None:
            self.iterable = iterable
            self.total = total
            self.desc = desc
            self.unit = unit
            self.n = initial

        def __iter__(self) -> Iterator[T]:
            if self.iterable is None:
                return
            for item in self.iterable:
                yield item
                self.update(1)

        def __enter__(self) -> "_FallbackTqdm":
            return self

        def __exit__(self, *_: Any) -> None:
            self.close()

        def update(self, n: int = 1) -> None:
            self.n += n

        def close(self) -> None:
            return None

        @staticmethod
        def write(message: str = "", file: Any | None = None, end: str = "\n", **_: Any) -> None:
            print(message, file=file or sys.stdout, end=end, flush=True)

    tqdm = _FallbackTqdm

