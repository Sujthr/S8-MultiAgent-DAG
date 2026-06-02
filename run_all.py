"""
run_all.py — S8 Assignment Runner

Executes all five assignment parts in order, logging each result.
Runs each query exactly ONCE — if a session-id file already exists for a
part, that part is skipped (idempotent re-runs).

Usage:
    python run_all.py              # run all parts
    python run_all.py --part 2    # run only Part 2
    python run_all.py --force     # ignore previous runs, re-run everything
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows (cp1252 can't encode box-drawing chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── path setup ────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent.resolve()
WORKSPACE_CODE = HERE / "workspace" / "code"
if not WORKSPACE_CODE.exists():
    print("ERROR: workspace/code not found.  Run setup.py first.")
    sys.exit(1)
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(WORKSPACE_CODE))

# ── local imports (after path is set) ─────────────────────────────────────────
import logger_setup as _ls
LOG = _ls.setup("s8-runner")

from queries_config import (
    QUERY_HELLO, QUERY_A, QUERY_I, QUERY_J, QUERY_K,
    QUERY_CRITIC_FAIL, QUERY_CRITIC_PASS,
    QUERY_CODER, QUERY_NEW_SKILL,
)

RESULTS_DIR = HERE / "logs" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Will be set to the current run's folder in main_async
_RUN_DIR: Path | None = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _result_file(part: str) -> Path:
    return RESULTS_DIR / f"part_{part}.json"


def _already_done(part: str) -> bool:
    f = _result_file(part)
    if not f.exists():
        return False
    try:
        data = json.loads(f.read_text())
        return data.get("success", False)
    except Exception:
        return False


def _save_result(part: str, query: str, answer: str, elapsed: float,
                 session_id: str, extra: dict | None = None) -> None:
    payload = {
        "part": part,
        "query": query,
        "answer": answer[:2000],
        "elapsed_s": round(elapsed, 2),
        "session_id": session_id,
        "success": bool(answer and answer.strip()),
        **(extra or {}),
    }
    data = json.dumps(payload, indent=2)
    # Save to flat location (idempotency reference)
    _result_file(part).write_text(data)
    # Save to per-run folder (archive)
    if _RUN_DIR is not None:
        (_RUN_DIR / f"part_{part}.json").write_text(data)
    LOG.info("Part %s saved -> logs/results/part_%s.json", part, part)


def _separator(title: str) -> None:
    LOG.info("")
    LOG.info("=" * 70)
    LOG.info("  %s", title)
    LOG.info("=" * 70)


def _inspect_graph(sid: str) -> dict:
    """Return a dict of skill→result info from the session graph."""
    try:
        from persistence import SessionStore
        store = SessionStore(sid)
        graph_nx = store.read_graph()
        if graph_nx is None:
            return {}
        out = {}
        for nid, data in graph_nx.nodes(data=True):
            skill = data.get("skill", "")
            r = data.get("result")
            out.setdefault(skill, []).append({
                "nid": nid,
                "status": data.get("status"),
                "elapsed": getattr(r, "elapsed_s", None) if r else None,
                "output": getattr(r, "output", None) if r else None,
            })
        return out
    except Exception:
        return {}


def _is_all_providers_exhausted(error_text: str) -> bool:
    return "all providers unavailable" in error_text.lower()


def _prompt_openai_key_cli() -> str | None:
    """Prompt for OpenAI key in CLI mode. Returns key or None."""
    if not sys.stdin.isatty():
        return None
    print("\n" + "=" * 60)
    print("  ALL FREE API PROVIDERS EXHAUSTED")
    print("  Enter your OpenAI API key to continue, or press Enter to skip.")
    print("  (Get one at: https://platform.openai.com/api-keys)")
    print("=" * 60)
    try:
        key = input("  OpenAI key (sk-...): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not key or not key.startswith("sk-"):
        print("  Skipping — invalid or empty key.")
        return None
    return key


def _save_openai_key(key: str) -> None:
    """Write OpenAI key to both .env files."""
    for env_path in [HERE / ".env", HERE / "workspace" / ".env"]:
        if not env_path.exists():
            continue
        text = env_path.read_text(encoding="utf-8")
        lines = []
        for line in text.splitlines():
            if line.startswith("OPENAI_API_KEY="):
                lines.append(f"OPENAI_API_KEY={key}")
            else:
                lines.append(line)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    LOG.info("OpenAI key saved to .env. Restart the gateway to apply: run stop.bat then start.bat")
    print("\n  Key saved! To use it, restart the gateway:")
    print("  1. Run stop.bat")
    print("  2. Run start.bat")
    print("  Or re-run from the UI (it will restart automatically).\n")


# ── query executor ────────────────────────────────────────────────────────────

async def _run_query(query: str, label: str) -> tuple[str, float, str]:
    """Run a single query through the orchestrator. Returns (answer, elapsed_s, session_id)."""
    from flow import Executor
    import uuid

    sid = f"s8-{label}-{uuid.uuid4().hex[:6]}"
    LOG.info("Running [%s]  session=%s", label, sid)
    LOG.debug("  query: %s", query[:120])

    t0 = time.time()
    try:
        executor = Executor()
        answer = await executor.run(query, session_id=sid)
    except Exception as exc:
        LOG.error("Query [%s] raised exception: %s", label, exc, exc_info=True)
        answer = f"ERROR: {exc}"
    elapsed = time.time() - t0
    LOG.info("Finished [%s] in %.1fs", label, elapsed)

    # Detect all-providers-exhausted and prompt for OpenAI key in CLI mode
    if _is_all_providers_exhausted(answer):
        key = _prompt_openai_key_cli()
        if key:
            _save_openai_key(key)

    return answer, elapsed, sid


# ── Part 1 ────────────────────────────────────────────────────────────────────

async def run_part1(force: bool = False) -> None:
    _separator("PART 1 — Base Queries (hello, A, I, J, K) — verbatim from Session 8 PDF")
    queries = [
        ("1_hello", "1hello", QUERY_HELLO,
         "minimal DAG: planner → formatter"),
        ("1_A",     "1A",     QUERY_A,
         "URL fetch → researcher → distiller → critic (auto) → formatter"),
        ("1_I",     "1I",     QUERY_I,
         "parallel researchers: London, Paris, Berlin → coder → formatter"),
        ("1_J",     "1J",     QUERY_J,
         "graceful failure: planner → formatter (2 nodes, no tool dispatch)"),
        ("1_K",     "1K",     QUERY_K,
         "parallel researchers: Lagos, Cairo, Kinshasa → coder → formatter"),
    ]
    for part_id, label, query, expected in queries:
        if not force and _already_done(part_id):
            LOG.info("Part %s already done — skipping", part_id)
            continue
        LOG.info("Query %s: %s", part_id, expected)
        answer, elapsed, sid = await _run_query(query, label)
        _save_result(part_id, query, answer, elapsed, sid,
                     extra={"expected": expected})


# ── Part 2 ────────────────────────────────────────────────────────────────────

async def run_part2(force: bool = False) -> None:
    _separator("PART 2 — Parallel Fan-out (London / Paris / Berlin)")
    if not force and _already_done("2"):
        LOG.info("Part 2 already done — skipping")
        return

    LOG.info("Parallel fan-out query (verbatim): %s", QUERY_I)
    t0 = time.time()
    answer, elapsed, sid = await _run_query(QUERY_I, "2-parallel")
    wall = time.time() - t0

    graph_info = _inspect_graph(sid)
    researcher_nodes = graph_info.get("researcher", [])
    concurrency_note = "DAG graph not available for inspection"
    if researcher_nodes:
        times = [n["elapsed"] for n in researcher_nodes if n["elapsed"] is not None]
        if times:
            max_branch = max(times)
            sum_branch = sum(times)
            concurrency_note = (
                f"researcher branch times: {[round(t,1) for t in times]} s | "
                f"max={max_branch:.1f}s  sum={sum_branch:.1f}s  wall={elapsed:.1f}s | "
                f"parallel={'YES — wall < sum' if elapsed < sum_branch * 0.8 else 'VERIFY'}"
            )
            LOG.info("Concurrency check: %s", concurrency_note)

    sandbox_nodes = graph_info.get("sandbox_executor", [])
    sandbox_note = "not found"
    if sandbox_nodes:
        out = sandbox_nodes[0].get("output") or {}
        sandbox_note = f"exit_code={out.get('exit_code')} stdout={str(out.get('stdout',''))[:200]}"

    _save_result("2", QUERY_I, answer, elapsed, sid,
                 extra={"wall_s": round(wall, 2),
                        "concurrency_note": concurrency_note,
                        "sandbox_note": sandbox_note})


# ── Part 3 ────────────────────────────────────────────────────────────────────

async def run_part3(force: bool = False) -> None:
    _separator("PART 3 — Critic FAIL then PASS (distiller auto-inserts critic)")

    if force or not _already_done("3_fail"):
        LOG.info("Run 1 (expected FAIL): sparse source → critic rejects → recovery planner fires")
        answer_fail, elapsed_fail, sid_fail = await _run_query(
            QUERY_CRITIC_FAIL, "3-fail")

        graph_info = _inspect_graph(sid_fail)
        critic_nodes = graph_info.get("critic", [])
        recovery_planners = [
            n for n in graph_info.get("planner", [])
            if n["nid"] != "n:1"
        ]
        critic_verdict = "no critic node found"
        if critic_nodes:
            out = critic_nodes[0].get("output") or {}
            critic_verdict = f"verdict={out.get('verdict','?')} rationale={str(out.get('rationale',''))[:150]}"

        LOG.info("Critic: %s", critic_verdict)
        LOG.info("Recovery planners fired: %d", len(recovery_planners))

        _save_result("3_fail", QUERY_CRITIC_FAIL, answer_fail,
                     elapsed_fail, sid_fail,
                     extra={"expected": "critic_fail_then_recovery_succeeds",
                            "critic_verdict": critic_verdict,
                            "recovery_planners": len(recovery_planners)})
    else:
        LOG.info("Part 3/fail already done — skipping")

    if force or not _already_done("3_pass"):
        LOG.info("Run 2 (expected PASS): complete source text → critic approves")
        answer_pass, elapsed_pass, sid_pass = await _run_query(
            QUERY_CRITIC_PASS, "3-pass")

        graph_info = _inspect_graph(sid_pass)
        critic_nodes = graph_info.get("critic", [])
        critic_verdict = "no critic node found"
        if critic_nodes:
            out = critic_nodes[0].get("output") or {}
            critic_verdict = f"verdict={out.get('verdict','?')} rationale={str(out.get('rationale',''))[:150]}"

        LOG.info("Critic: %s", critic_verdict)

        _save_result("3_pass", QUERY_CRITIC_PASS, answer_pass,
                     elapsed_pass, sid_pass,
                     extra={"expected": "critic_pass",
                            "critic_verdict": critic_verdict})
    else:
        LOG.info("Part 3/pass already done — skipping")


# ── Part 4 ────────────────────────────────────────────────────────────────────

async def run_part4(force: bool = False) -> None:
    _separator("PART 4 — Coder + SandboxExecutor (compound interest computation)")
    if not force and _already_done("4"):
        LOG.info("Part 4 already done — skipping")
        return

    LOG.info("Coder query: %s", QUERY_CODER)
    answer, elapsed, sid = await _run_query(QUERY_CODER, "4-coder")

    graph_info = _inspect_graph(sid)
    sandbox_nodes = graph_info.get("sandbox_executor", [])
    coder_nodes = graph_info.get("coder", [])

    sandbox_note = "(sandbox node not found in graph)"
    coder_note = "(coder node not found in graph)"

    if coder_nodes:
        out = coder_nodes[0].get("output") or {}
        code_snippet = str(out.get("code", ""))[:300]
        coder_note = f"code_length={len(code_snippet)} summary={str(out.get('summary',''))[:100]}"
        LOG.info("Coder output: %s", coder_note)

    if sandbox_nodes:
        out = sandbox_nodes[0].get("output") or {}
        sandbox_note = (
            f"exit_code={out.get('exit_code')} | "
            f"stdout={str(out.get('stdout', ''))[:300]}"
        )
        LOG.info("SandboxExecutor: %s", sandbox_note)

    _save_result("4", QUERY_CODER, answer, elapsed, sid,
                 extra={"coder_note": coder_note,
                        "sandbox_note": sandbox_note})


# ── Part 5 ────────────────────────────────────────────────────────────────────

async def run_part5(force: bool = False) -> None:
    _separator("PART 5 — New Skill: table_extractor (YAML + prompt only, no Python changes)")
    if not force and _already_done("5"):
        LOG.info("Part 5 already done — skipping")
        return

    LOG.info("New skill query: %s", QUERY_NEW_SKILL[:100])
    answer, elapsed, sid = await _run_query(QUERY_NEW_SKILL, "5-table")

    graph_info = _inspect_graph(sid)
    skills_used = sorted(graph_info.keys())
    table_used = "table_extractor" in graph_info

    LOG.info("Skills in graph: %s", skills_used)
    LOG.info("table_extractor used: %s", table_used)

    _save_result("5", QUERY_NEW_SKILL, answer, elapsed, sid,
                 extra={"skills_used": skills_used,
                        "table_extractor_used": table_used})


# ── main ──────────────────────────────────────────────────────────────────────

async def main_async(parts: list[int], force: bool) -> None:
    global _RUN_DIR

    # Create a timestamped folder for this run's results
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _RUN_DIR = RESULTS_DIR / f"run_{run_ts}"
    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOG.info("Run folder: %s", _RUN_DIR)

    runners = {
        1: run_part1,
        2: run_part2,
        3: run_part3,
        4: run_part4,
        5: run_part5,
    }
    total_start = time.time()
    for p in parts:
        try:
            await runners[p](force=force)
        except KeyboardInterrupt:
            LOG.warning("Interrupted — run again to resume (results saved per-part)")
            break
        except Exception as exc:
            LOG.error("Part %d failed with unhandled exception: %s", p, exc, exc_info=True)
            LOG.error("Continuing to next part ...")

    LOG.info("")
    LOG.info("All requested parts complete.  Total time: %.1fs", time.time() - total_start)
    LOG.info("Results: %s", RESULTS_DIR)
    LOG.info("Run archive: %s", _RUN_DIR)

    # Copy run folder to "latest"
    latest = RESULTS_DIR / "latest"
    if latest.exists():
        shutil.rmtree(latest)
    shutil.copytree(_RUN_DIR, latest)

    # Print summary table
    print("\n" + "─" * 70)
    print(f"{'Part':<12} {'Status':<12} {'Elapsed':>10}  Session")
    print("─" * 70)
    for fname in sorted(RESULTS_DIR.glob("part_*.json")):
        try:
            d = json.loads(fname.read_text())
            status = "DONE" if d.get("success") else "FAIL"
            print(f"{d['part']:<12} {status:<12} {d['elapsed_s']:>9.1f}s  {d.get('session_id','')}")
        except Exception:
            pass
    print("─" * 70 + "\n")
    print(f"Run archive saved to: {_RUN_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="S8 Assignment Runner")
    parser.add_argument("--part", type=int, choices=[1, 2, 3, 4, 5],
                        help="Run only this part (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if already done")
    args = parser.parse_args()

    parts = [args.part] if args.part else [1, 2, 3, 4, 5]
    asyncio.run(main_async(parts, force=args.force))


if __name__ == "__main__":
    main()
