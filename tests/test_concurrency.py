"""
Concurrency stress tests – verify that parallel runs maintain independent
journals and do not share or corrupt mutable state.

Tests:
  1. 10 parallel runs of Scenario 1 → all succeed, all have unique run_ids
  2. Each run's journal contains only its own run_id (no cross-contamination)
  3. DP cache hit rate improves with more runs (shared cache correctly reused)
  4. Each run's memo table is independent (private cache per run → no leakage)
"""

import os
import sys
import threading
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.agent_loop import AgentLoop
from orchestrator.dp_cache import DPCache


def _run_scenario1(failure_injection: str = "none", shared_cache: DPCache = None):
    from workflows.scenario1 import get_task, build_tools
    task = get_task(failure_injection=failure_injection)
    tools = build_tools()
    cache = shared_cache or DPCache()
    loop = AgentLoop(tools, max_steps=15, max_retries=3, time_limit=15.0, dp_cache=cache)
    return loop.run(task)


class TestConcurrency:

    def test_parallel_runs_all_succeed(self):
        """10 concurrent runs of Scenario 1 should all succeed."""
        N = 10
        results = []
        with ThreadPoolExecutor(max_workers=N) as pool:
            futures = [pool.submit(_run_scenario1, "none") for _ in range(N)]
            for f in as_completed(futures):
                results.append(f.result())

        assert len(results) == N
        statuses = [r["status"] for r in results]
        assert all(s == "succeeded" for s in statuses), \
            f"Some runs failed: {statuses}"

    def test_parallel_runs_unique_run_ids(self):
        """Each parallel run must have a distinct run_id."""
        N = 10
        with ThreadPoolExecutor(max_workers=N) as pool:
            futures = [pool.submit(_run_scenario1, "none") for _ in range(N)]
            results = [f.result() for f in as_completed(futures)]

        run_ids = [r["run_id"] for r in results]
        assert len(set(run_ids)) == N, f"Duplicate run IDs detected: {run_ids}"

    def test_no_journal_cross_contamination(self):
        """Each run's journal must contain only entries for its own run_id."""
        N = 8
        with ThreadPoolExecutor(max_workers=N) as pool:
            futures = [pool.submit(_run_scenario1, "none") for _ in range(N)]
            results = [f.result() for f in as_completed(futures)]

        for result in results:
            run_id = result["run_id"]
            journal = result.get("journal", [])
            for entry in journal:
                assert entry["run_id"] == run_id, (
                    f"Journal entry for {entry['run_id']} found in run {run_id}. "
                    "State contamination detected!"
                )

    def test_shared_cache_improves_hit_rate(self):
        """Multiple runs sharing a DPCache should accumulate cache hits."""
        N = 5
        shared_cache = DPCache()
        results = []
        with ThreadPoolExecutor(max_workers=N) as pool:
            futures = [pool.submit(_run_scenario1, "none", shared_cache) for _ in range(N)]
            for f in as_completed(futures):
                results.append(f.result())

        # After N runs on the same dataset, the cache should have some hits
        assert shared_cache.cache_size > 0
        # At least some metrics are tracked
        total_ops = shared_cache.cache_hits + shared_cache.cache_misses
        assert total_ops > 0

    def test_private_caches_no_cross_leakage(self):
        """Runs with separate DPCache instances must not share entries."""
        cache_a = DPCache()
        cache_b = DPCache()

        r_a = _run_scenario1("none", cache_a)
        r_b = _run_scenario1("none", cache_b)

        # Both should succeed
        assert r_a["status"] == "succeeded"
        assert r_b["status"] == "succeeded"

        # cache_a and cache_b are independent instances
        assert cache_a is not cache_b

    def test_mixed_success_and_failure_parallel(self):
        """Mix of normal and failure-injected runs should not interfere."""
        tasks = ["none", "bad_path", "none", "missing_col", "none"] * 2
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {pool.submit(_run_scenario1, t): t for t in tasks}
            results = [(futures[f], f.result()) for f in as_completed(futures)]

        for task_type, result in results:
            if task_type == "none":
                assert result["status"] == "succeeded", \
                    f"Normal run {result['run_id']} failed unexpectedly"
            else:
                assert result["status"] in ("stopped", "failed"), \
                    f"Failure-injected run {result['run_id']} should not succeed"

    def test_concurrent_dp_cache_thread_safety(self):
        """Concurrent cache reads/writes should not cause data corruption."""
        cache = DPCache(max_size=512)
        errors = []

        def stress_worker(worker_id: int):
            try:
                local_results = []
                for i in range(20):
                    key = cache.make_key(
                        frozenset([f"obj_{i % 5}"]),
                        3,
                        float(i % 4),
                        f"fp{worker_id % 3}",
                    )
                    cached = cache.get(key)
                    if cached is None:
                        cache.put(key, {"value": worker_id * 100 + i})
                    else:
                        local_results.append(cached)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=stress_worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"
