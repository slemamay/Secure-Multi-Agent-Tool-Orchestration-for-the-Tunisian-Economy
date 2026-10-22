"""
DPCache – Dynamic Programming memoization for the orchestration planner.

Key design:
    Cache key = (frozenset of completed objectives, budget_class, data_fingerprint)

    - "completed_objectives" identifies the planning sub-problem.
    - "budget_class" discretises the remaining budget (time + retries) so that
      we do not cache on exact float values (which would never hit).
    - "data_fingerprint" is the MD5 of the raw dataset so we never serve a
      cached KPI result if the underlying data changed.

Two runs that map to the same key WILL produce the same downstream result,
so reuse is safe and correct.

Metrics tracked:
    cache_hits, cache_misses, cache_size
"""

import threading
from functools import lru_cache
from typing import Any, Dict, FrozenSet, Optional, Tuple

# Budget is discretised into N classes (coarser = more cache hits)
_BUDGET_CLASSES = 5  # e.g., retries 0-3 → class 0; time 0-3s → class 0 ...


def _discretise_budget(retries_remaining: int, time_remaining: float) -> Tuple[int, int]:
    """Map continuous budget values to discrete classes."""
    r_class = min(retries_remaining, _BUDGET_CLASSES)
    t_class = min(int(time_remaining // 3), _BUDGET_CLASSES)   # 3-second buckets
    return r_class, t_class


class DPCache:
    """
    Thread-safe DP memoization table for repeated planning subproblems.

    Usage:
        cache = DPCache()
        key = cache.make_key({"read_data"}, retries_left=3, time_left=12.5, fingerprint="abc")
        cached = cache.get(key)
        if cached is None:
            result = compute_kpis(...)
            cache.put(key, result)
    """

    def __init__(self, max_size: int = 256):
        self._table: Dict[Tuple, Any] = {}
        self._max_size = max_size
        self._lock = threading.Lock()
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    # ── Key construction ──────────────────────────────────────────────────────

    def make_key(
        self,
        completed_objectives: FrozenSet[str],
        retries_remaining: int,
        time_remaining: float,
        data_fingerprint: str = "",
    ) -> Tuple:
        """
        Build a canonical cache key.
        Two runs map to the same key iff they have the same objective subset,
        same budget class, and the same input data.
        """
        r_class, t_class = _discretise_budget(retries_remaining, time_remaining)
        return (
            completed_objectives,   # frozenset is hashable
            r_class,
            t_class,
            data_fingerprint,
        )

    # ── Cache operations ──────────────────────────────────────────────────────

    def get(self, key: Tuple) -> Optional[Any]:
        with self._lock:
            if key in self._table:
                self.cache_hits += 1
                return self._table[key]
            self.cache_misses += 1
            return None

    def put(self, key: Tuple, value: Any) -> None:
        with self._lock:
            if len(self._table) >= self._max_size:
                # Simple eviction: remove oldest entry (first inserted)
                oldest = next(iter(self._table))
                del self._table[oldest]
            self._table[key] = value

    def invalidate(self, data_fingerprint: str) -> int:
        """Remove all entries associated with a specific data fingerprint."""
        with self._lock:
            to_remove = [k for k in self._table if k[3] == data_fingerprint]
            for k in to_remove:
                del self._table[k]
            return len(to_remove)

    def clear(self) -> None:
        with self._lock:
            self._table.clear()
            self.cache_hits = 0
            self.cache_misses = 0

    # ── Statistics ────────────────────────────────────────────────────────────

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._table)

    @property
    def hit_ratio(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    def stats(self) -> Dict[str, Any]:
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_size": self.cache_size,
            "hit_ratio": round(self.hit_ratio, 4),
        }


# ── Module-level shared cache (shared across runs within a session) ───────────
# Individual runs should pass their own cache to prevent cross-contamination.
_shared_cache: Optional[DPCache] = None


def get_shared_cache() -> DPCache:
    global _shared_cache
    if _shared_cache is None:
        _shared_cache = DPCache()
    return _shared_cache
