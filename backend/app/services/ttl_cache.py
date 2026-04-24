"""Generic in-process TTL cache with stampede protection.

Mirrors the pattern in ``app.services.cost_tracking.pricing_cache`` but carries
no domain knowledge. Consumers instantiate a module-level singleton per domain
and call ``get_or_load(key, loader)``.

Guarantees:
1. TTL-based expiry — always eventually consistent.
2. Per-key asyncio lock — coalesces concurrent cold-start loads so only one
   loader fires per miss.
3. LRU trimming — bounded memory via ``max_entries``.

The loader callable is responsible for all I/O; the cache never blocks the
event loop itself. If the loader raises, the exception propagates without
caching a sentinel, so the next caller re-attempts.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Awaitable, Callable, Generic, Hashable, TypeVar

_log = logging.getLogger(__name__)

K = TypeVar('K', bound=Hashable)
V = TypeVar('V')


class _Entry(Generic[V]):
    __slots__ = ('value', 'expires_at')

    def __init__(self, value: V, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class _MissingType:
    pass


_MISSING = _MissingType()


class TTLCache(Generic[K, V]):
    """LRU cache with TTL and per-key asyncio locks."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int = 1024,
        name: str = 'ttl_cache',
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._name = name
        self._entries: OrderedDict[K, _Entry[V]] = OrderedDict()
        self._locks: dict[K, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _get_fresh(self, key: K):
        entry = self._entries.get(key)
        if entry is None:
            return _MISSING
        if entry.expires_at < time.monotonic():
            self._entries.pop(key, None)
            return _MISSING
        self._entries.move_to_end(key)
        return entry.value

    def _put(self, key: K, value: V) -> None:
        self._entries[key] = _Entry(value, time.monotonic() + self._ttl)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    async def get_or_load(self, key: K, loader: Callable[[], Awaitable[V]]) -> V:
        """Return cached value if fresh; otherwise await ``loader`` and cache."""
        cached = self._get_fresh(key)
        if cached is not _MISSING:
            return cached  # type: ignore[return-value]

        lock = await self._get_lock(key)
        async with lock:
            cached = self._get_fresh(key)
            if cached is not _MISSING:
                return cached  # type: ignore[return-value]
            value = await loader()
            self._put(key, value)
            return value

    async def _get_lock(self, key: K) -> asyncio.Lock:
        async with self._global_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def invalidate(self, key: K | None = None) -> None:
        """Drop a specific key, or the entire cache when ``key`` is None."""
        if key is None:
            self._entries.clear()
            _log.debug('%s: invalidated all', self._name)
        else:
            self._entries.pop(key, None)
            _log.debug('%s: invalidated key', self._name)

    def size(self) -> int:
        return len(self._entries)


__all__ = ['TTLCache']
