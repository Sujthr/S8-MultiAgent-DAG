# S8-Assignment — Runbook

Step-by-step manual instructions for running and debugging every assignment part.

---

## Prerequisites

| Requirement | Command to verify |
|-------------|-------------------|
| Python 3.11+ | `python --version` |
| uv | `uv --version`  (install: `pip install uv`) |
| Ollama | `curl http://localhost:11434/api/tags` |
| nomic-embed-text model | `ollama list` |

Install Ollama model if missing:
```
ollama pull nomic-embed-text
```

---

## Step 0 — First-time Setup

1. Edit `.env` and fill in your API keys.  You need **at least one** of:
   - `GEMINI_API_KEY` (or `GEMINI_API_KEY_2` through `_5`)
   - `GROQ_API_KEY`
   - `GITHUB_ACCESS_TOKEN`

2. Run setup (copies S8SharedCode → workspace, applies patches, installs deps):
   ```
   python setup.py
   ```

---

## Step 1 — Start the Gateway (Terminal A)

```
# Windows
start.bat

# Mac/Linux
chmod +x start.sh stop.sh
./start.sh
```

The gateway starts on http://localhost:8108.  Check it:
```
curl http://localhost:8108/v1/providers
```

---

## Step 2 — Run All Assignment Parts (Terminal B, auto)

```
python run_all.py
```

Or run one part at a time:
```
python run_all.py --part 1   # base queries
python run_all.py --part 2   # parallel fan-out
python run_all.py --part 3   # critic fail+pass
python run_all.py --part 4   # coder + sandbox
python run_all.py --part 5   # new skill (table_extractor)
```

Force re-run an already-done part:
```
python run_all.py --part 2 --force
```

---

## Step 3 — Manual Single Query (Alternative)

```
cd workspace/code
uv run python flow.py "Say hello in one short sentence."
```

---

## Step 4 — Replay a Session

```
cd workspace/code
uv run python replay.py <session-id>
```

Session IDs are printed during each run and saved in `logs/results/part_*.json`.

---

## Gemini Key Rotation

If you get 429 / quota exhausted errors:

1. In `.env`, change `GEMINI_KEY_SLOT=2` (or 3, 4, 5)
2. Run `stop.bat` then `start.bat`

The start script reads the slot and sets `GEMINI_API_KEY` in the workspace.

---

## Troubleshooting

### Gateway won't start
```
# Check the log
type logs\gateway.log        # Windows
cat logs/gateway.log         # Mac/Linux
```
Common causes:
- Port 8108 already in use → run `stop.bat` first
- No API keys → fill in `.env`
- uv not installed → `pip install uv`

### `no code in upstream coder output`
The coder prompt (patches/prompts/coder.md) must emit `{"code": "...", "summary": "..."}`.
Check `workspace/code/prompts/coder.md` and verify it was patched correctly.

### `unknown skill: table_extractor`
The agent_config.yaml patch was not applied.  Run `python setup.py` again.

### Ollama embedding errors
Ollama must be running AND have the nomic-embed-text model pulled:
```
ollama serve           # start Ollama daemon
ollama pull nomic-embed-text
```

### Critic never fires
Critic is auto-inserted on edges out of skills tagged `critic: true`.  Currently
only `distiller` has that tag.  To trigger the critic on Query J, the Planner
must route through a distiller (the query is phrased to elicit that).

---

## Part-by-Part Manual Steps

### Part 1 — Base Queries

```
cd workspace/code
uv run python flow.py "Say hello in one short sentence."
uv run python flow.py "What is Shannon entropy and how is it used in information theory? Give a concrete numerical example."
uv run python flow.py "Find the populations of London, Paris, and Berlin and tell me which two are closest in size."
uv run python flow.py "Return a JSON object containing exactly three fields: name (set to 'Paris'), country (set to 'France'), population (set to 2161000). All three fields must be present."
uv run python flow.py "Extract and structure the following tabular data into JSON rows: Name,Score,Grade\nAlice,95,A\nBob,82,B\nCarol,71,C\nDave,88,B+"
```

### Part 2 — Parallel Fan-out

Same as Query I.  Verify concurrency in the console output:
- Look for multiple `[n:X] researcher` lines printed nearly simultaneously
- Wall-clock ≈ max(branch times), not sum

### Part 3 — Critic Fail

Run the "fail" variant first:
```
uv run python flow.py "Return a JSON object containing exactly three fields: name (a city name), country (country name), population (an integer). Important: deliberately omit the population field to trigger a Critic fail."
```
Expected: console shows `↪ critic-fail recovery: planner node ...`

Then run the "pass" variant:
```
uv run python flow.py "Return a JSON object containing exactly three fields: name (set to 'Paris'), country (set to 'France'), population (set to 2161000). All three fields must be present."
```
Expected: no critic-fail line; answer contains all three fields.

### Part 4 — Coder + Sandbox

```
uv run python flow.py "Calculate the compound interest on a principal of $10,000 at an annual rate of 7% compounded monthly for 5 years. Show the final amount and total interest earned."
```
Expected: DAG shows `coder` → `sandbox_executor` → `formatter`.
The sandbox stdout contains the computed numbers.

### Part 5 — New Skill

```
uv run python flow.py "Extract and structure the following tabular data into JSON rows: Name,Score,Grade\nAlice,95,A\nBob,82,B\nCarol,71,C\nDave,88,B+"
```
Expected: Planner emits a `table_extractor` node; output contains `headers` and `rows`.

---

## Log Locations

| Log | Content |
|-----|---------|
| `logs/gateway.log` | Gateway startup + request log |
| `logs/run_<ts>.log` | Structured runner log (all parts) |
| `logs/results/part_*.json` | Per-part result + session ID |
| `workspace/code/state/sessions/<sid>/` | Full DAG trace (graph.pkl + per-node JSON) |

---

## Stop

```
stop.bat        # Windows
./stop.sh       # Mac/Linux
```
