import time
from typing import Any, Callable


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() > expires_at:
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic() + self._ttl, value)

    def delete(self, key: str) -> None:
        self._items.pop(key, None)

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        value = self.get(key)
        if value is None:
            value = factory()
            self.set(key, value)
        return value
