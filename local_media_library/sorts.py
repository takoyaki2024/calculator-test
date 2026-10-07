from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class SortOption(Generic[T]):
    key: str
    label: str
    order: Callable[[T], object]
    reverse: bool = False


class SortRegistry(Generic[T]):
    def __init__(self) -> None:
        self._options: dict[str, SortOption[T]] = {}

    def register(self, option: SortOption[T]) -> None:
        if option.key in self._options:
            raise ValueError(f"duplicate sort: {option.key}")
        self._options[option.key] = option

    def options(self) -> tuple[SortOption[T], ...]:
        return tuple(self._options.values())

    def apply(self, items: Iterable[T], key: str) -> list[T]:
        option = self._options[key]
        return sorted(items, key=option.order, reverse=option.reverse)


def default_registry() -> SortRegistry:
    registry = SortRegistry()
    registry.register(SortOption("newest", "新着順", lambda item: (item.mtime_ns, item.title.casefold()), True))
    registry.register(SortOption("oldest", "古い順", lambda item: (item.mtime_ns, item.title.casefold())))
    registry.register(SortOption("title", "タイトル順", lambda item: item.title.casefold()))
    return registry
