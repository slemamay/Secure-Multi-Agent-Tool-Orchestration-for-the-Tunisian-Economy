"""
Week 3 – Full GUI: Tunisia Multi-Agent Orchestration System
Run with:  python -m streamlit run gui/app.py
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="Tunisia Orchestrator – Week 3",
    page_icon="🇹🇳",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "runs" not in st.session_state:
    st.session_state.runs = []

@st.cache_resource
def get_shared_dp_cache():
    from orchestrator.dp_cache import DPCache
    return DPCache()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("🇹🇳 Tunisia Orchestrator")
st.sidebar.markdown("**Week 3 – Robustness, DP & Concurrency**")
page = st.sidebar.radio("Navigation", [
    "Task Launcher",
    "Run Overview",
    "Step Timeline",
    "Tool Inspector",
    "Safety & Policy",
    "Metrics & BT vs DP",
    "Failure Injection Console",
])

# ── Failure mode options per scenario ────────────────────────────────────────
S1_MODES = {
    "none":           "✅ No injection (normal run)",
    "bad_path":       "❌ Bad file path → FileNotFoundError → RETRY * 3 → STOP",
    "missing_col":    "⚠️ Wrong columns → SchemaValidationError → STOP",
    "division_by_zero": "➗ Empty dataset → Division by zero in KPI calc → STOP",
}
S2_MODES = {
    "none":           "✅ No injection (normal run)",
    "api_timeout":    "⏱ API Timeout → ToolExecutionError → RETRY * 3 → STOP",
    "api_rate_limit": "🚫 HTTP 429 Rate Limit → RETRY * 3 → STOP",
    "bad_path":       "❌ Bad CSV path → FileNotFoundError → STOP",
}


def _execute_run(scenario_name, failure_mode, cache_obj):
    """Run a scenario and return the result dict."""
    try:
        from orchestrator.agent_loop import AgentLoop
        from orchestrator.dp_cache import DPCache
        from orchestrator.failure_injector import FailureInjector

        dp = cache_obj if cache_obj is not None else DPCache()

        if "Scenario 1" in scenario_name:
            from workflows.scenario1 import get_task, build_tools
            task   = get_task(failure_injection=failure_mode)
            tools  = build_tools()
            injector = FailureInjector("none")           # S1 failures are task-level
        else:
            from workflows.scenario2 import get_task, build_tools, get_failure_injector
            task     = get_task()                        # always clean task
            tools    = build_tools()
            injector = get_failure_injector(failure_mode)  # S2 failures via injector

        loop   = AgentLoop(tools, max_steps=15, max_retries=3, time_limit=15.0,
                           dp_cache=dp, failure_injector=injector)
        result = loop.run(task)
        result["scenario"]      = scenario_name
        result["failure_mode"]  = failure_mode
        return result

    except Exception as exc:
        import traceback
        return {
            "run_id": "ERROR", "status": "failed", "error": str(exc),
            "scenario": scenario_name, "failure_mode": failure_mode,
            "journal": [], "planner_stats": {}, "dp_cache_stats": {},
            "output": None, "elapsed_seconds": 0, "dp_hits_this_run": 0,
            "_traceback": traceback.format_exc(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 1 – Task Launcher
# ══════════════════════════════════════════════════════════════════════════════
if page == "Task Launcher":
    st.title("Task Launcher")

    col1, col2 = st.columns([2, 1])
    with col1:
        scenario = st.selectbox("Scenario", [
            "Scenario 1 – Tourism KPI Dashboard",
            "Scenario 2 – Overnight Stays Indicator Pull",
        ])
        # Show ONLY valid failure modes for the chosen scenario
        modes = S1_MODES if "Scenario 1" in scenario else S2_MODES
        failure_mode = st.selectbox("Failure Injection", list(modes.keys()),
                                    format_func=lambda k: modes[k])
        use_shared   = st.toggle("Share DP cache across runs", value=True)
        concurrency  = st.slider("Parallel runs", 1, 10, 1)

    with col2:
        st.metric("Max Steps",   "15")
        st.metric("Max Retries", "3")
        st.metric("Time Limit",  "15 s")

    if st.button(" Launch Run(s)", use_container_width=True, type="primary"):
        cache = get_shared_dp_cache() if use_shared else None

        if concurrency == 1:
            with st.spinner("Running…"):
                result = _execute_run(scenario, failure_mode, cache)
                st.session_state.runs.append(result)

            if result["status"] == "succeeded":
                st.success(f"✅ {result['run_id']} succeeded in {result['elapsed_seconds']:.2f}s")
                out = result.get("output") or {}
                if "top_region" in out:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Top Region", out.get("top_region", "—"))
                    c2.metric("Regions",    len(out.get("occupancy_rate_by_region", {})))
                    c3.metric("Alerts",     len(out.get("alerts", [])))
                elif "trend" in out:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Trend",     out.get("trend", "—").capitalize())
                    c2.metric("Peak Year", out.get("peak_year", "—"))
                    c3.metric("Nationalities", len(out.get("growth_rates", {})))
                st.json(out)
            else:
                st.error(f"❌ {result['run_id']} {result['status'].upper()}: {result.get('error','')}")
                if result.get("_traceback"):
                    st.code(result["_traceback"])

                # Show retry evidence in journal
                st.subheader("📓 Execution Journal (failure evidence)")
                _COLOR = {"PLAN":"🔵","TOOL_CALL":"🟠","RESULT":"🟢","ERROR":"🔴","STOP":"⬛"}
                for e in result.get("journal", []):
                    evt  = e.get("event","?")
                    data = e.get("data",{})
                    msg  = data.get("message") or data.get("summary") or data.get("reason") or data.get("rationale","")
                    st.markdown(f"`{e['step_id']}` {_COLOR.get(evt,'⚪')} **{evt}** → {data.get('tool','')} {msg}")
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with st.spinner(f"Running {concurrency} parallel runs…"):
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [pool.submit(_execute_run, scenario, failure_mode, cache)
                               for _ in range(concurrency)]
                    for f in as_completed(futures):
                        st.session_state.runs.append(f.result())
            last_n  = st.session_state.runs[-concurrency:]
            ok      = sum(1 for r in last_n if r["status"] == "succeeded")
            st.success(f"✅ {ok}/{concurrency} runs succeeded")
            run_ids = [r["run_id"] for r in last_n]
            st.info(f"Run IDs (all unique: {len(set(run_ids))==concurrency}): {', '.join(run_ids)}")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 2 – Run Overview
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Run Overview":
    st.title("Run Overview")
    runs = st.session_state.runs
    if not runs:
        st.info("No runs yet. Use Task Launcher to start a run.")
    else:
        for run in reversed(runs):
            icon = "✅" if run["status"] == "succeeded" else "❌"
            with st.expander(
                f"{icon} {run['run_id']} – {run.get('scenario','?')} "
                f"[{run.get('failure_mode','?')}] – {run['status'].upper()}",
                expanded=False,
            ):
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Status",        run["status"].upper())
                c2.metric("Journal Steps", len(run.get("journal",[])))
                c3.metric("Duration",      f"{run.get('elapsed_seconds',0):.3f}s")
                c4.metric("DP Hits",       run.get("dp_hits_this_run",0))

                bt = run.get("planner_stats",{})
                dp = run.get("dp_cache_stats",{})
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("**Planner (BT)**")
                    st.write(f"Explored: {bt.get('branches_explored',0)} | "
                             f"Pruned: {bt.get('branches_pruned',0)} | "
                             f"Rate: {bt.get('pruning_rate',0):.1%}")
                with col_b:
                    st.markdown("**DP Cache**")
                    st.write(f"Hits: {dp.get('cache_hits',0)} | "
                             f"Misses: {dp.get('cache_misses',0)} | "
                             f"Ratio: {dp.get('hit_ratio',0):.1%}")
                if run.get("error"):
                    st.error(f"Error: {run['error']}")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 3 – Step Timeline
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Step Timeline":
    st.title("Step Timeline")
    runs = st.session_state.runs
    if not runs:
        st.info("No runs yet.")
    else:
        selected_id = st.selectbox("Select Run", [r["run_id"] for r in reversed(runs)])
        run = next(r for r in runs if r["run_id"] == selected_id)

        _C = {"PLAN":"🔵","TOOL_CALL":"🟠","RESULT":"🟢","ERROR":"🔴","STOP":"⬛"}
        _R = {"PLAN":"Planner","TOOL_CALL":"Executor","RESULT":"Executor","ERROR":"Critic","STOP":"Critic"}

        st.caption(f"Status: **{run['status']}** | "
                   f"Duration: {run.get('elapsed_seconds',0):.3f}s | "
                   f"Steps: {len(run.get('journal',[]))}")

        for e in run.get("journal",[]):
            evt  = e.get("event","?")
            data = e.get("data",{})
            desc = (data.get("rationale") or data.get("summary") or
                    data.get("message")   or data.get("reason",""))
            col1, col2 = st.columns([1,6])
            with col1:
                st.markdown(f"`{e['step_id']}` {_C.get(evt,'⚪')} **{_R.get(evt,'—')}**")
            with col2:
                st.markdown(f"`{e['timestamp'][:19]}` `{evt}` → **{data.get('tool','')}** {desc}")
            with st.expander("Raw JSON", expanded=False):
                st.json(e)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 4 – Tool Inspector
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Tool Inspector":
    st.title("Tool-Call Inspector")
    runs = st.session_state.runs
    if not runs:
        st.info("No runs yet.")
    else:
        selected_id = st.selectbox("Select Run", [r["run_id"] for r in reversed(runs)])
        run = next(r for r in runs if r["run_id"] == selected_id)

        calls   = [e for e in run.get("journal",[]) if e["event"] == "TOOL_CALL"]
        results = [e for e in run.get("journal",[]) if e["event"] in ("RESULT","ERROR")]

        st.markdown(f"**{len(calls)} tool invocation(s)**")
        for tc in calls:
            sid   = tc["step_id"]
            tname = tc["data"].get("tool","?")
            match = next((r for r in results if r["step_id"] == sid), None)
            icon  = "🟢" if (match and match["event"]=="RESULT") else "🔴"
            with st.expander(f"{icon} {sid} – {tname}", expanded=True):
                c1,c2 = st.columns(2)
                with c1:
                    st.markdown("**Inputs**")
                    st.json(tc["data"].get("inputs",{}))
                with c2:
                    if match:
                        st.markdown(f"**{match['event']}**")
                        st.json(match["data"])
                    else:
                        st.warning("No result recorded.")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 5 – Safety & Policy
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Safety & Policy":
    st.title("Safety & Policy Panel")

    from security.allow_list import ALLOWED_PATH_PREFIXES, ALLOWED_API_HOSTS
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("Allowed File Path Prefixes")
        for p in sorted(ALLOWED_PATH_PREFIXES): st.code(p)
    with c2:
        st.subheader("Allowed API Hosts")
        for h in sorted(ALLOWED_API_HOSTS): st.code(h)

    st.subheader("Constraint Limits")
    st.table({"Constraint":["Max Steps","Max Retries","Time Limit","Max Response Size"],
              "Value":["15","3","15 s","1 MB"]})

    st.subheader("Security Controls")
    for check, status in {
        "Path traversal prevention":  "✅ Path.resolve() before allow-list check",
        "Sensitive field redaction":   "✅ Keys: password, token, secret, key, api_key, auth",
        "Input schema validation":     "✅ jsonschema on all tool inputs",
        "Output schema validation":    "✅ jsonschema on all tool outputs",
        "Per-run isolation":           "✅ Each RunManager instance is independent",
        "API allow-list enforcement":  "✅ Only allow-listed hostnames permitted",
    }.items():
        st.markdown(f"- **{check}**: {status}")

    # Show security events from runs
    runs = st.session_state.runs
    if runs:
        st.subheader("Safety Events in Runs")
        errors = [(r["run_id"],e["data"].get("message",""))
                  for r in runs for e in r.get("journal",[]) if e["event"]=="ERROR"]
        if errors:
            for rid, msg in errors:
                if any(k in msg.lower() for k in ["permission","security","allow-list","traversal"]):
                    st.error(f"[{rid}] 🛡 Security block: {msg}")
                else:
                    st.warning(f"[{rid}] ⚠️ Tool error: {msg}")
        else:
            st.success("No errors in any run yet.")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 6 – Metrics & BT vs DP
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Metrics & BT vs DP":
    st.title("Metrics & BT vs DP Comparison")
    runs = st.session_state.runs
    if not runs:
        st.info("No runs yet.")
    else:
        total     = len(runs)
        succeeded = sum(1 for r in runs if r["status"]=="succeeded")
        avg_lat   = sum(r.get("elapsed_seconds",0) for r in runs)/total
        dp_hits   = sum(r.get("dp_hits_this_run",0) for r in runs)

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Total Runs",  total)
        c2.metric("Succeeded",   succeeded)
        c3.metric("Failed",      total-succeeded)
        c4.metric("Avg Latency", f"{avg_lat:.3f}s")
        c5.metric("Total DP Hits", dp_hits)

        st.subheader("Per-Run BT vs DP Table")
        rows = []
        for r in runs:
            bt = r.get("planner_stats",{})
            dp = r.get("dp_cache_stats",{})
            rows.append({
                "Run ID":       r["run_id"],
                "Status":       r["status"],
                "Failure Mode": r.get("failure_mode","—"),
                "Duration (s)": round(r.get("elapsed_seconds",0),4),
                "BT Explored":  bt.get("branches_explored",0),
                "BT Pruned":    bt.get("branches_pruned",0),
                "BT Pruning %": f"{bt.get('pruning_rate',0):.1%}",
                "DP Hits":      dp.get("cache_hits",0),
                "DP Hit %":     f"{dp.get('hit_ratio',0):.1%}",
                "DP Size":      dp.get("cache_size",0),
            })
        try:
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        except ImportError:
            st.json(rows)

        cache = get_shared_dp_cache()
        cs    = cache.stats()
        st.subheader("Shared DP Cache")
        cc1,cc2,cc3,cc4 = st.columns(4)
        cc1.metric("Cache Size",   cs["cache_size"])
        cc2.metric("Total Hits",   cs["cache_hits"])
        cc3.metric("Total Misses", cs["cache_misses"])
        cc4.metric("Hit Ratio",    f"{cs['hit_ratio']:.1%}")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 7 – Failure Injection Console
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Failure Injection Console":
    st.title("Failure Injection Console")
    st.markdown("Trigger failure modes and observe retry + recovery in the journal.")

    c1,c2 = st.columns(2)
    with c1:
        fi_scenario = st.selectbox("Scenario", ["Scenario 1","Scenario 2"])
        modes       = S1_MODES if fi_scenario=="Scenario 1" else S2_MODES
        fi_mode     = st.selectbox("Failure Mode", list(modes.keys()),
                                   format_func=lambda k: modes[k])
    with c2:
        st.markdown("**Expected behavior**")
        expected = {
            "none":             "Normal run → SUCCESS",
            "bad_path":         "FileNotFound → RETRY (×3) → STOP_FAILURE",
            "missing_col":      "Wrong columns → schema mismatch → STOP_FAILURE immediately",
            "division_by_zero": "Empty dataset injected → KPI calc fails → STOP_FAILURE",
            "api_timeout":      "Timeout → RETRY (×3) → STOP_FAILURE",
            "api_rate_limit":   "HTTP 429 → RETRY (×3) → STOP_FAILURE",
        }
        st.info(expected.get(fi_mode, "—"))

    if st.button("💥 Inject & Run", type="primary"):
        scenario_name = f"{fi_scenario} – {'Tourism KPI Dashboard' if fi_scenario=='Scenario 1' else 'Overnight Stays'}"
        with st.spinner("Injecting failure…"):
            result = _execute_run(scenario_name, fi_mode, None)
            st.session_state.runs.append(result)

        status_icon = "✅" if result["status"]=="succeeded" else "❌"
        st.markdown(f"### {status_icon} Run `{result['run_id']}` — **{result['status'].upper()}**")

        # Always show full journal for this page
        st.subheader("📓 Execution Journal")
        _C = {"PLAN":"🔵","TOOL_CALL":"🟠","RESULT":"🟢","ERROR":"🔴","STOP":"⬛"}
        for e in result.get("journal",[]):
            evt  = e.get("event","?")
            data = e.get("data",{})
            tool = data.get("tool","")
            msg  = (data.get("message") or data.get("summary") or
                    data.get("reason")  or data.get("rationale",""))
            st.markdown(f"`{e['step_id']}` {_C.get(evt,'⚪')} **{evt}** → {tool} — {msg}")

        # Summary stats
        errors   = [e for e in result.get("journal",[]) if e["event"]=="ERROR"]
        retries  = [e for e in result.get("journal",[]) if e["event"]=="TOOL_CALL"]
        st.markdown(f"**Tool calls:** {len(retries)} | **Errors logged:** {len(errors)}")
        if len(retries) > 1 and fi_mode != "none":
            st.success(f"✅ Retry mechanism confirmed: {len(retries)} attempts made")
        if result.get("error"):
            st.error(f"Final error: {result['error']}")



