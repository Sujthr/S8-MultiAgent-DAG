"""
ui.py — S8 Assignment Web UI

A simple Flask web UI to run and monitor the S8 assignment parts.
Start with:  python ui.py
Then open:   http://localhost:5000
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# ── try to import Flask, install if missing ───────────────────────────────────
try:
    from flask import Flask, Response, jsonify, render_template_string, request, stream_with_context
except ImportError:
    print("Flask not found — installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "--quiet"])
    from flask import Flask, Response, jsonify, render_template_string, request, stream_with_context

HERE = Path(__file__).parent.resolve()
RESULTS_DIR = HERE / "logs" / "results"

# ── global run state ──────────────────────────────────────────────────────────
_run_lock = threading.Lock()
_run_proc: subprocess.Popen | None = None
_log_lines: list[str] = []
_run_done = False

app = Flask(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_gateway_status() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:8108/health", timeout=2)
        return True
    except Exception:
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8108/v1/routers", timeout=2)
            return True
        except Exception:
            return False


def _get_results() -> dict:
    results = {}
    if not RESULTS_DIR.exists():
        return results
    for f in sorted(RESULTS_DIR.glob("part_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results[data["part"]] = data
        except Exception:
            pass
    return results


def _get_run_history() -> list[str]:
    if not RESULTS_DIR.exists():
        return []
    return sorted(
        [d.name for d in RESULTS_DIR.iterdir() if d.is_dir() and d.name.startswith("run_")],
        reverse=True
    )[:10]


def _openai_key() -> str:
    env_path = HERE / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def _save_openai_key(key: str) -> None:
    for env_path in [HERE / ".env", HERE / "workspace" / ".env"]:
        if not env_path.exists():
            continue
        text = env_path.read_text(encoding="utf-8")
        lines = []
        replaced = False
        for line in text.splitlines():
            if line.startswith("OPENAI_API_KEY="):
                lines.append(f"OPENAI_API_KEY={key}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"OPENAI_API_KEY={key}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _restart_gateway() -> None:
    """Kill existing gateway and start a new one."""
    stop = HERE / "stop.bat"
    start_gw = HERE / "start_gateway.bat"
    if stop.exists():
        subprocess.run(["cmd", "/c", str(stop)], capture_output=True, cwd=str(HERE))
        time.sleep(2)
    if start_gw.exists():
        subprocess.Popen(["cmd", "/c", str(start_gw)], cwd=str(HERE))


# ── HTML template ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>S8 Multi-Agent DAG — Assignment Runner</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d2e; --border: #2d3148;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #6366f1;
    --green: #22c55e; --red: #ef4444; --yellow: #f59e0b;
    --blue: #3b82f6; --purple: #a855f7;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }
  header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1rem 1.5rem; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 1.2rem; font-weight: 600; letter-spacing: -0.01em; }
  .gateway-pill { display: flex; align-items: center; gap: .5rem; font-size: .8rem; color: var(--muted); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
  .dot.ok { background: var(--green); }
  main { max-width: 1100px; margin: 0 auto; padding: 1.5rem; display: grid; gap: 1.5rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; }
  .card-title { font-size: .75rem; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin-bottom: 1rem; }
  /* Buttons */
  .btn-row { display: flex; flex-wrap: wrap; gap: .5rem; }
  .btn { display: inline-flex; align-items: center; gap: .4rem; padding: .45rem .9rem; border-radius: 8px; font-size: .85rem; font-weight: 500; cursor: pointer; border: none; transition: opacity .15s; }
  .btn:hover { opacity: .85; }
  .btn:disabled { opacity: .4; cursor: not-allowed; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-secondary { background: var(--border); color: var(--text); }
  .btn-danger  { background: var(--red); color: #fff; }
  .btn-success { background: var(--green); color: #000; }
  /* Part cards */
  .parts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
  .part-card { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; }
  .part-card.done   { border-color: var(--green); }
  .part-card.running { border-color: var(--yellow); }
  .part-card.failed { border-color: var(--red); }
  .part-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: .5rem; }
  .part-name { font-weight: 600; font-size: .9rem; }
  .part-badge { font-size: .7rem; font-weight: 700; padding: .2rem .5rem; border-radius: 20px; text-transform: uppercase; }
  .badge-done    { background: rgba(34,197,94,.15); color: var(--green); }
  .badge-running { background: rgba(245,158,11,.15); color: var(--yellow); }
  .badge-failed  { background: rgba(239,68,68,.15);  color: var(--red); }
  .badge-pending { background: rgba(148,163,184,.1); color: var(--muted); }
  .part-meta { font-size: .75rem; color: var(--muted); margin-top: .35rem; }
  .part-answer { margin-top: .6rem; font-size: .78rem; color: var(--text); background: rgba(0,0,0,.3); border-radius: 6px; padding: .5rem .7rem; max-height: 80px; overflow: hidden; cursor: pointer; white-space: pre-wrap; word-break: break-word; }
  .part-answer.expanded { max-height: 300px; overflow-y: auto; }
  /* Log */
  #log { background: #080a0f; border-radius: 8px; padding: 1rem; height: 320px; overflow-y: auto; font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: .75rem; line-height: 1.6; }
  .log-info { color: #94a3b8; }
  .log-done { color: var(--green); }
  .log-err  { color: var(--red); }
  .log-sep  { color: var(--purple); }
  /* OpenAI section */
  .key-row { display: flex; gap: .5rem; margin-top: .75rem; }
  .key-input { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: .45rem .8rem; color: var(--text); font-size: .85rem; outline: none; }
  .key-input:focus { border-color: var(--accent); }
  .key-hint { font-size: .75rem; color: var(--muted); margin-top: .4rem; }
  /* History */
  .history-row { display: flex; flex-wrap: wrap; gap: .4rem; }
  .history-chip { font-size: .7rem; background: rgba(99,102,241,.1); border: 1px solid rgba(99,102,241,.3); color: var(--accent); padding: .15rem .5rem; border-radius: 20px; cursor: pointer; }
  .history-chip:hover { background: rgba(99,102,241,.2); }
  /* Toast */
  #toast { position: fixed; bottom: 1.5rem; right: 1.5rem; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: .7rem 1rem; font-size: .85rem; opacity: 0; transition: opacity .3s; pointer-events: none; z-index: 999; }
  #toast.show { opacity: 1; }
</style>
</head>
<body>
<header>
  <h1>S8 Multi-Agent DAG — Assignment Runner</h1>
  <div class="gateway-pill">
    <div class="dot" id="gw-dot"></div>
    <span id="gw-label">Checking gateway...</span>
  </div>
</header>
<main>
  <!-- Run Controls -->
  <div class="card">
    <div class="card-title">Run Controls</div>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="runAll()">Run All Parts</button>
      <button class="btn btn-secondary" onclick="runPart(1)">Part 1</button>
      <button class="btn btn-secondary" onclick="runPart(2)">Part 2</button>
      <button class="btn btn-secondary" onclick="runPart(3)">Part 3</button>
      <button class="btn btn-secondary" onclick="runPart(4)">Part 4</button>
      <button class="btn btn-secondary" onclick="runPart(5)">Part 5</button>
      <button class="btn btn-danger"    onclick="runForce()">Force Re-run All</button>
    </div>
  </div>

  <!-- Part Status -->
  <div class="card">
    <div class="card-title">Assignment Parts</div>
    <div class="parts-grid" id="parts-grid">
      <div class="part-card" id="part-1_hello"><div class="part-header"><span class="part-name">1a — hello</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Say hello.</div></div>
      <div class="part-card" id="part-1_A"><div class="part-header"><span class="part-name">1b — Query A</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Wikipedia fetch + distiller</div></div>
      <div class="part-card" id="part-1_I"><div class="part-header"><span class="part-name">1c — Query I</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">London/Paris/Berlin parallel</div></div>
      <div class="part-card" id="part-1_J"><div class="part-header"><span class="part-name">1d — Query J</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Graceful failure</div></div>
      <div class="part-card" id="part-1_K"><div class="part-header"><span class="part-name">1e — Query K</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Lagos/Cairo/Kinshasa parallel</div></div>
      <div class="part-card" id="part-2"><div class="part-header"><span class="part-name">2 — Parallel Fan-out</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Concurrency timing proof</div></div>
      <div class="part-card" id="part-3_fail"><div class="part-header"><span class="part-name">3a — Critic FAIL</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Fail then recovery then corrected answer</div></div>
      <div class="part-card" id="part-3_pass"><div class="part-header"><span class="part-name">3b — Critic PASS</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Complete source then critic approves</div></div>
      <div class="part-card" id="part-4"><div class="part-header"><span class="part-name">4 — Coder + Sandbox</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">Compound interest + SandboxExecutor</div></div>
      <div class="part-card" id="part-5"><div class="part-header"><span class="part-name">5 — table_extractor</span><span class="part-badge badge-pending">pending</span></div><div class="part-meta">New skill: CSV to JSON</div></div>
    </div>
  </div>

  <!-- Live Log -->
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
      <div class="card-title" style="margin:0">Live Log</div>
      <div style="display:flex;gap:.5rem">
        <button class="btn btn-secondary" onclick="clearLog()" style="padding:.3rem .7rem;font-size:.75rem">Clear</button>
        <button class="btn btn-secondary" onclick="scrollLog()" style="padding:.3rem .7rem;font-size:.75rem">Bottom</button>
      </div>
    </div>
    <div id="log"></div>
  </div>

  <!-- Run History -->
  <div class="card" id="history-card" style="display:none">
    <div class="card-title">Run History</div>
    <div class="history-row" id="history-row"></div>
  </div>

  <!-- OpenAI Fallback Key -->
  <div class="card">
    <div class="card-title">OpenAI API Key — Paid Fallback</div>
    <p style="font-size:.82rem;color:var(--muted);margin-bottom:.75rem">
      When all free providers (Gemini, Groq, Cerebras, NVIDIA) are exhausted, the system
      falls back to OpenAI. Leave blank to use only free providers.
    </p>
    <div class="key-row">
      <input class="key-input" type="password" id="openai-key" placeholder="sk-..." />
      <button class="btn btn-success" onclick="saveKey()">Save Key</button>
      <button class="btn btn-secondary" onclick="restartGateway()">Restart Gateway</button>
    </div>
    <div class="key-hint" id="key-hint"></div>
  </div>
</main>
<div id="toast"></div>

<script>
let _es = null;
let _polling = null;

// ── toast ─────────────────────────────────────────────────────────────────────
function toast(msg, dur=3000) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), dur);
}

// ── log ──────────────────────────────────────────────────────────────────────
function appendLog(line) {
  const el = document.getElementById('log');
  const div = document.createElement('div');
  let cls = 'log-info';
  if (line.includes('PART ') || line.includes('===')) cls = 'log-sep';
  else if (line.includes('saved') || line.includes('DONE') || line.includes('complete')) cls = 'log-done';
  else if (line.includes('ERROR') || line.includes('failed') || line.includes('FAIL')) cls = 'log-err';
  div.className = cls;
  div.textContent = line;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}
function clearLog() { document.getElementById('log').innerHTML = ''; }
function scrollLog() { const el=document.getElementById('log'); el.scrollTop=el.scrollHeight; }

// ── SSE stream ────────────────────────────────────────────────────────────────
function startStream() {
  if (_es) { _es.close(); _es = null; }
  _es = new EventSource('/api/stream');
  _es.onmessage = e => {
    if (e.data === '__DONE__') {
      _es.close(); _es = null;
      fetchStatus();
      return;
    }
    appendLog(e.data);
  };
  _es.onerror = () => { if (_es) { _es.close(); _es = null; } };
}

// ── run controls ──────────────────────────────────────────────────────────────
async function runAll()   { await startRun({}); }
async function runForce() { await startRun({force: true}); }
async function runPart(n) { await startRun({part: n}); }

async function startRun(body) {
  clearLog();
  appendLog('Starting run...');
  const r = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const d = await r.json();
  if (d.error) { toast(d.error); return; }
  startStream();
  startPolling();
}

// ── status polling ────────────────────────────────────────────────────────────
function startPolling() {
  if (_polling) clearInterval(_polling);
  _polling = setInterval(fetchStatus, 3000);
}

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    updateGateway(d.gateway);
    updateParts(d.results);
    updateHistory(d.history);
    if (!d.running && _polling) {
      clearInterval(_polling); _polling = null;
    }
    // Check key status
    document.getElementById('key-hint').textContent =
      d.openai_key ? 'OpenAI key is set' : 'No OpenAI key — free providers only';
  } catch(e) {}
}

function updateGateway(ok) {
  document.getElementById('gw-dot').className = 'dot' + (ok ? ' ok' : '');
  document.getElementById('gw-label').textContent = ok ? 'Gateway running' : 'Gateway offline';
}

function updateParts(results) {
  for (const [part, data] of Object.entries(results)) {
    const card = document.getElementById('part-' + part);
    if (!card) continue;
    const badge = card.querySelector('.part-badge');
    const ok = data.success;
    card.className = 'part-card ' + (ok ? 'done' : 'failed');
    badge.className = 'part-badge ' + (ok ? 'badge-done' : 'badge-failed');
    badge.textContent = ok ? data.elapsed_s + 's' : 'failed';
    // Show answer preview
    let answerEl = card.querySelector('.part-answer');
    if (!answerEl) {
      answerEl = document.createElement('div');
      answerEl.className = 'part-answer';
      answerEl.onclick = () => answerEl.classList.toggle('expanded');
      card.appendChild(answerEl);
    }
    answerEl.textContent = data.answer || '(no answer)';
    // Show concurrency note for Part 2
    if (part === '2' && data.concurrency_note) {
      const meta = card.querySelector('.part-meta');
      if (meta) meta.textContent = data.concurrency_note;
    }
    // Show critic verdict for Part 3
    if ((part === '3_fail' || part === '3_pass') && data.critic_verdict) {
      const meta = card.querySelector('.part-meta');
      if (meta) meta.textContent = data.critic_verdict;
    }
    // Show sandbox note for Part 4
    if (part === '4' && data.sandbox_note) {
      const meta = card.querySelector('.part-meta');
      if (meta) meta.textContent = data.sandbox_note.slice(0, 80);
    }
    // Show table_extractor used for Part 5
    if (part === '5') {
      const meta = card.querySelector('.part-meta');
      if (meta) meta.textContent = data.table_extractor_used ? 'table_extractor used' : 'table_extractor NOT used';
    }
  }
}

function updateHistory(history) {
  const card = document.getElementById('history-card');
  const row = document.getElementById('history-row');
  if (!history || !history.length) { card.style.display = 'none'; return; }
  card.style.display = '';
  row.innerHTML = history.map(h =>
    '<span class="history-chip" title="' + h + '">' + h.replace('run_','') + '</span>'
  ).join('');
}

// ── OpenAI key ────────────────────────────────────────────────────────────────
async function saveKey() {
  const key = document.getElementById('openai-key').value.trim();
  if (!key) { toast('Enter a key first'); return; }
  const r = await fetch('/api/key/openai', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({key})});
  const d = await r.json();
  if (d.error) { toast(d.error); return; }
  toast('Key saved! Restart the gateway to apply.');
  document.getElementById('key-hint').textContent = 'Key saved — restart gateway to activate';
}

async function restartGateway() {
  toast('Restarting gateway...');
  const r = await fetch('/api/gateway/restart', {method:'POST'});
  const d = await r.json();
  toast(d.message || 'Gateway restarting...');
  setTimeout(fetchStatus, 8000);
}

// ── init ──────────────────────────────────────────────────────────────────────
fetchStatus();
setInterval(fetchStatus, 10000);
</script>
</body>
</html>"""


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/status")
def api_status():
    return jsonify({
        "gateway": _get_gateway_status(),
        "running": bool(_run_proc and _run_proc.poll() is None),
        "results": _get_results(),
        "history": _get_run_history(),
        "openai_key": bool(_openai_key()),
    })


@app.route("/api/run", methods=["POST"])
def api_run():
    global _run_proc, _log_lines, _run_done

    with _run_lock:
        if _run_proc and _run_proc.poll() is None:
            return jsonify({"error": "A run is already in progress"}), 409

    data = request.get_json(silent=True) or {}
    part = data.get("part")
    force = data.get("force", False)

    cmd = [sys.executable, str(HERE / "run_all.py")]
    if part:
        cmd += ["--part", str(part)]
    if force:
        cmd += ["--force"]

    _log_lines = []
    _run_done = False

    def _do_run():
        global _run_proc, _run_done
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(HERE), text=True, bufsize=1,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        with _run_lock:
            _run_proc = proc
        for line in proc.stdout:
            _log_lines.append(line.rstrip())
        proc.wait()
        _run_done = True

    threading.Thread(target=_do_run, daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/stream")
def api_stream():
    def generate():
        sent = 0
        while True:
            new_lines = _log_lines[sent:]
            for line in new_lines:
                yield f"data: {json.dumps(line)}\n\n"
                sent += 1
            if _run_done and sent >= len(_log_lines):
                yield "data: __DONE__\n\n"
                return
            time.sleep(0.15)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/key/openai", methods=["POST"])
def api_key_openai():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    if not key.startswith("sk-"):
        return jsonify({"error": "Key must start with sk-"}), 400
    _save_openai_key(key)
    return jsonify({"saved": True})


@app.route("/api/gateway/restart", methods=["POST"])
def api_gateway_restart():
    def _do_restart():
        stop = HERE / "stop.bat"
        start_gw = HERE / "start_gateway.bat"
        if stop.exists():
            subprocess.run(["cmd", "/c", str(stop)], capture_output=True, cwd=str(HERE))
            time.sleep(2)
        if start_gw.exists():
            subprocess.Popen(["cmd", "/c", str(start_gw)], cwd=str(HERE))

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"message": "Gateway restarting — wait ~15 seconds"})


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser
    port = int(os.getenv("UI_PORT", "5000"))
    print(f"\n{'='*55}")
    print(f"  S8 Assignment Runner — Web UI")
    print(f"  Open: http://localhost:{port}")
    print(f"{'='*55}\n")
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
