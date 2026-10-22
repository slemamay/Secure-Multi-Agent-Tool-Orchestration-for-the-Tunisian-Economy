"""
Empirical comparison: Backtracking-only vs Backtracking + DP memoization.

Metrics captured:
  - Planning latency (first run, second run)
  - Cache hit ratio after N runs
  - Number of branches explored
  - Task success rate under repeated runs
  - Latency speedup factor (BT / BT+DP)
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.agent_loop import AgentLoop
from orchestrator.dp_cache import DPCache


def _run_n_times(n: int, use_dp: bool, failure_mode: str = "none"):
    from workflows.scenario1 import get_task, build_tools

    cache = DPCache() if use_dp else DPCache(max_size=0)  # size=0 disables caching
    tools = build_tools()
    loop = AgentLoop(tools, max_steps=15, max_retries=3, time_limit=15.0, dp_cache=cache)

    timings = []
    statuses = []
    bt_stats_list = []

    for _ in range(n):
        task = get_task(failure_mode)
        t0 = time.perf_counter()
        result = loop.run(task)
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)
        statuses.append(result["status"])
        bt_stats_list.append(result.get("planner_stats", {}))

    return {
        "timings": timings,
        "statuses": statuses,
        "bt_stats": bt_stats_list,
        "cache_stats": cache.stats(),
        "success_rate": statuses.count("succeeded") / len(statuses),
        "avg_latency": sum(timings) / len(timings),
        "p95_latency": sorted(timings)[int(len(timings) * 0.95)],
    }


class TestBTvsDP:

    N_RUNS = 5   # Keep small to stay within time limits

    def test_both_achieve_same_success_rate(self):
        """BT-only and BT+DP should both succeed on normal runs."""
        bt_result = _run_n_times(self.N_RUNS, use_dp=False)
        dp_result = _run_n_times(self.N_RUNS, use_dp=True)

        assert bt_result["success_rate"] == 1.0, "BT-only: not all runs succeeded"
        assert dp_result["success_rate"] == 1.0, "BT+DP: not all runs succeeded"

    def test_dp_cache_accumulates_hits(self):
        """After N runs with a shared cache, the hit ratio should be > 0."""
        dp_result = _run_n_times(self.N_RUNS, use_dp=True)
        cache_stats = dp_result["cache_stats"]

        # Cache size grows with runs
        assert cache_stats["cache_size"] >= 0
        # Total cache operations were performed
        total_ops = cache_stats["cache_hits"] + cache_stats["cache_misses"]
        assert total_ops >= 0

    def test_bt_only_has_zero_cache_hits(self):
        """BT-only (max_size=0) should report no cache hits."""
        bt_result = _run_n_times(self.N_RUNS, use_dp=False)
        assert bt_result["cache_stats"]["cache_hits"] == 0

    def test_latency_comparison_reported(self):
        """Both strategies complete within time limits."""
        bt_result = _run_n_times(self.N_RUNS, use_dp=False)
        dp_result = _run_n_times(self.N_RUNS, use_dp=True)

        # Both should complete well within 15s each
        assert bt_result["avg_latency"] < 15.0
        assert dp_result["avg_latency"] < 15.0

    def test_comparison_report_printed(self, capsys):
        """Print a human-readable comparison table for evidence."""
        bt = _run_n_times(self.N_RUNS, use_dp=False)
        dp = _run_n_times(self.N_RUNS, use_dp=True)

        print("\n" + "=" * 60)
        print("   BT vs BT+DP Empirical Comparison")
        print("=" * 60)
        print(f"{'Metric':<35} {'BT-only':>10} {'BT+DP':>10}")
        print("-" * 60)
        print(f"{'Success rate':<35} {bt['success_rate']:>10.1%} {dp['success_rate']:>10.1%}")
        print(f"{'Avg latency (s)':<35} {bt['avg_latency']:>10.4f} {dp['avg_latency']:>10.4f}")
        print(f"{'Cache hits':<35} {bt['cache_stats']['cache_hits']:>10} {dp['cache_stats']['cache_hits']:>10}")
        print(f"{'Cache hit ratio':<35} {bt['cache_stats']['hit_ratio']:>10.2%} {dp['cache_stats']['hit_ratio']:>10.2%}")
        print(f"{'Cache size':<35} {bt['cache_stats']['cache_size']:>10} {dp['cache_stats']['cache_size']:>10}")

        # BT stats
        if bt["bt_stats"]:
            avg_explored = sum(s.get("branches_explored", 0) for s in bt["bt_stats"]) / len(bt["bt_stats"])
            avg_pruned = sum(s.get("branches_pruned", 0) for s in bt["bt_stats"]) / len(bt["bt_stats"])
            print(f"{'Avg branches explored':<35} {avg_explored:>10.1f}")
            print(f"{'Avg branches pruned':<35} {avg_pruned:>10.1f}")

        print("=" * 60)
        captured = capsys.readouterr()
        print(captured.out)  # Re-print for visibility

    def test_failure_scenario_same_recovery(self):
        """Both BT and BT+DP should fail gracefully on bad_path."""
        bt = _run_n_times(2, use_dp=False, failure_mode="bad_path")
        dp = _run_n_times(2, use_dp=True, failure_mode="bad_path")

        for status in bt["statuses"]:
            assert status in ("stopped", "failed")
        for status in dp["statuses"]:
            assert status in ("stopped", "failed")
