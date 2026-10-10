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
    sql_order: str | None = None


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

    def sql_order(self, key: str, alias: str) -> str:
        """Only Core-registered SQL is accepted; UI supplies the registry key."""
        expression = self._options[key].sql_order
        if expression is None:
            raise ValueError(f"sort has no paged query implementation: {key}")
        return expression.format(alias=alias)


def default_registry() -> SortRegistry:
    registry = SortRegistry()
    registry.register(SortOption("newest", "新着順", lambda item: (item.mtime_ns, item.title.casefold()), True,
                                "{alias}.mtime_ns DESC,{alias}.title COLLATE CASEFOLD DESC,{alias}.id DESC"))
    registry.register(SortOption("oldest", "古い順", lambda item: (item.mtime_ns, item.title.casefold()),
                                sql_order="{alias}.mtime_ns,{alias}.title COLLATE CASEFOLD,{alias}.id"))
    registry.register(SortOption("title", "タイトル順", lambda item: item.title.casefold(),
                                sql_order="{alias}.title COLLATE CASEFOLD,{alias}.id"))
    return registry


def video_registry() -> SortRegistry:
    from .natural import natural_key
    registry = default_registry()
    registry.register(SortOption("natural", "ファイル名順", lambda item: natural_key(item.title),
                                 sql_order="{alias}.title COLLATE NATURAL_ORDER,{alias}.id"))
    return registry
