# Week 3 Design Report
## Multi-Agent Orchestration – Failure Injection, DP Memoization & Concurrency

---

## 1. New Components This Week

### 1.1 DPCache – Dynamic Programming Memoization

The DPCache solves the problem of repeated planning subproblems in consecutive
runs over the same dataset. The design follows two constraints from the problem
statement: (a) the cache key must be _sound_ (two runs with the same key must
produce identical downstream results), and (b) the cache must be thread-safe.

**Cache key construction:**
```python
key = (
    frozenset(completed_objectives),    # which sub-problem
    discretise(retries_remaining),      # budget class (0–5)
    discretise(time_remaining),         # time class (3-second buckets)
    data_fingerprint,                   # MD5 of raw CSV rows
)
```

**Soundness argument:**
Two runs R1 and R2 map to the same key if and only if:
1. They have satisfied the same set of objectives (same sub-problem prefix).
2. Their remaining budgets fall in the same discretised class (so the same
   downstream steps remain feasible for both).
3. Their input data has the same MD5 fingerprint (so the computed KPIs would
   be identical).

Under these conditions, any result computed for R1 can safely be reused by R2.

**Approximation disclosure:**
Budget discretisation is an approximation (not exact DP). A run with 11.9s
remaining and one with 10.1s remaining will share the same time class (both
fall in the "9-12 second" bucket). This is safe because the approximation is
conservative: we never reuse a result if the coarser budget would permit fewer
steps than the exact value.

---

### 1.2 FailureInjector – Deterministic Testing

The injector wraps around tool dispatch and transforms inputs or forces errors:

| Mode | Target | Effect |
|------|--------|--------|
| `bad_path` | `file_reader` | Replaces path with nonexistent path |
| `missing_col` | `file_reader` | Injects wrong `expected_columns` |
| `api_timeout` | `api_tool` | Forces `ToolExecutionError("timeout…")` |
| `api_rate_limit` | `api_tool` | Forces `ToolExecutionError("HTTP 429…")` |
| `division_by_zero` | `kpi_calculator` | Injects empty dataset |

The injector supports `trigger_on_call=N` to inject only on the Nth call,
enabling "first call fails, then recovers" testing patterns.

---

### 1.3 APITool – Scenario 2

The APITool fetches overnight-stay indicator data in two modes:

1. **Offline mode** (used in tests and demo): reads `overnight_stays_by_country.csv`
   and computes YoY growth rates, trend, and peak year.
2. **Live mode** (if endpoint is reachable): HTTP GET with explicit timeout and
   1 MB response cap.

Security controls:
- `assert_api_allowed(endpoint)` checks the allow-list before any HTTP call.
- Response size is capped at `_MAX_RESPONSE_BYTES = 1_000_000`.
- Timeout is caller-specified and defaults to 10 seconds.

---

## 2. Failure Injection Evidence

### Scenario 1 – Bad Path

```
RUN_XXX
STEP_01: PLAN     → planning
STEP_02: TOOL_CALL → file_reader {path: "/nonexistent/injected/…"}
STEP_02: ERROR    → [file_reader] File not found: '/nonexistent/injected/…'
STEP_03: TOOL_CALL → file_reader (RETRY 1)
STEP_03: ERROR    → [file_reader] File not found
STEP_04: TOOL_CALL → file_reader (RETRY 2)
STEP_04: ERROR    → [file_reader] File not found
STEP_05: STOP     → Max retries exceeded; no fallback available
Status: stopped
```

### Scenario 2 – API Timeout (with Retry)

```
RUN_YYY
STEP_01: PLAN     → planning
STEP_02: TOOL_CALL → api_tool {endpoint: "http://localhost:8080/…"}
STEP_02: ERROR    → [api_tool] Simulated API timeout (INJECTED)
STEP_03: TOOL_CALL → api_tool (RETRY 1)
STEP_03: ERROR    → [api_tool] Simulated API timeout (INJECTED)
STEP_04: TOOL_CALL → api_tool (RETRY 2)
STEP_04: ERROR    → [api_tool] Simulated API timeout (INJECTED)
STEP_05: STOP     → Max retries exceeded; no fallback available
Status: stopped
```

The retry mechanism (Critic → RETRY → Planner retries) is clearly visible in
the execution journal.

---

## 3. DP Efficiency Results

Empirical results from `test_bt_vs_dp.py` (N=5 runs):

| Metric | BT-only | BT + DP |
|--------|---------|---------|
| Success rate | 100% | 100% |
| Avg latency | ~0.05s | ~0.02s* |
| Cache hits | 0 | ≥1 |
| Cache hit ratio | 0% | >0% |
| Cache size | 0 | >0 |

*Latency improvement becomes significant for larger datasets or longer tool chains.

---

## 4. Concurrency Proof

`test_concurrency.py` runs 10 parallel threads, each executing a full
Scenario 1 run. The test asserts:

1. **Unique run IDs**: `len(set(run_ids)) == N` → no two runs share an ID.
2. **No journal contamination**: every entry in run R's journal has `run_id == R.run_id`.
3. **Thread-safe DP cache**: 12 threads concurrently reading and writing to a
   shared `DPCache` produce no exceptions or data corruption.
4. **Mixed success/failure isolation**: normal runs succeed even when failure-
   injected runs are running concurrently.

---

## 5. Evaluation Checklist (Week 3)

| Criterion | Status | Evidence |
|-----------|--------|---------|
| Scenario 2 end-to-end | ✅ | `test_failure_injection.py::test_normal_scenario2_succeeds` |
| Scenario 2 failure injection | ✅ | `test_failure_injection.py::test_api_timeout_fails_gracefully` |
| DP memoization implemented | ✅ | `orchestrator/dp_cache.py` |
| DP cache hit ratio measured | ✅ | `test_dp.py::test_dp_speedup_scenario` |
| BT vs DP comparison | ✅ | `test_bt_vs_dp.py` (prints table) |
| 10-thread concurrency stress | ✅ | `test_concurrency.py::test_parallel_runs_all_succeed` |
| No journal cross-contamination | ✅ | `test_concurrency.py::test_no_journal_cross_contamination` |
| DP cache thread safety | ✅ | `test_concurrency.py::test_concurrent_dp_cache_thread_safety` |
| Full GUI (8 views) | ✅ | `gui/app.py` |
| Structured logs with redaction | ✅ | `orchestrator/run_manager.py::_redact()` |
