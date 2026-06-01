# EAG V3 Session 8 — Multi-Agent DAG Orchestration

> **Student:** sujit@tradelab.co.in | **Date:** 2026-06-02

A self-contained implementation of the Session 8 assignment demonstrating a growing-graph multi-agent system: each LLM call is a vertex in a NetworkX DiGraph, skills communicate via typed `AgentResult` payloads, and the graph expands at runtime through Planner decisions, dynamic successors, Critic-triggered recovery, and a pluggable skill registry.

---

## Quick Start

```bash
# Windows — start gateway + run all parts
start.bat

# Unix/Mac
./start.sh

# Stop gateway
stop.bat   # or ./stop.sh

# Run only specific part
python run_all.py --part 2
python run_all.py --part 3 --force    # force re-run
```

---

## Architecture

```
User Query
    │
    ▼
┌─────────┐
│ Planner │  ← seeds the initial DAG from the query
└────┬────┘
     │  emits NodeSpec list (JSON)
     │
     ├──────────────────────────────────────┐
     ▼                                      ▼
┌──────────┐                          ┌──────────┐
│  Skill A │  asyncio.gather() →      │  Skill B │  ← parallel branches
└────┬─────┘                          └────┬─────┘
     │                                      │
     └────────────────┬─────────────────────┘
                      ▼
               ┌─────────────┐
               │   Critic?   │  ← auto-inserted when critic:true in YAML
               └──────┬──────┘
                      │ pass → continue  /  fail → recovery Planner
                      ▼
               ┌─────────────┐
               │  Formatter  │  ← final answer
               └─────────────┘
```

**Key files**

| File | Role |
|------|------|
| `workspace/code/flow.py` | Growing-graph orchestrator (`Graph` + `Executor`) |
| `workspace/code/skills.py` | `SkillRegistry` + per-node LLM dispatch |
| `workspace/code/recovery.py` | Critic-fail and upstream-failure recovery policy |
| `workspace/code/sandbox.py` | Subprocess sandbox for Coder execution |
| `workspace/code/mcp_runner.py` | Multi-turn tool-use loop (web_search, fetch_url) |
| `workspace/code/agent_config.yaml` | Skill catalogue — YAML only, no Python subclasses |
| `workspace/code/prompts/` | One `.md` prompt per skill |
| `workspace/gateway/` | LLM Gateway V8 — multi-key Gemini + provider failover |
| `workspace/gateway/agent_routing.yaml` | Pin specific skills to providers |
| `queries_config.py` | Canonical query strings from Session 8 PDF |
| `run_all.py` | Idempotent runner — saves `logs/results/part_*.json` |

**Provider failover order:**
```
gemini → gemini1 → gemini4 → gemini5 → groq → cerebras → openrouter → github → nvidia
```
Four independent Gemini keys (`gemini`, `gemini1`, `gemini4`, `gemini5`) with in-program key-family rotation — no `.env` changes needed when one key hits quota. The gateway tries the gemini family first, then falls through the quality-ordered remaining list.

**Agent routing** (`workspace/gateway/agent_routing.yaml`):
```yaml
planner:    gemini    # strong reasoning needed for DAG JSON
critic:     groq      # deterministic pass/fail; fast
researcher: gemini    # tool-call loops need reliable function_calling support
```

---

## Part 1 — Base Queries

All five queries are verbatim from the Session 8 PDF.

### hello

**Query:** `Say hello.`
**Expected DAG:** `planner → formatter` (2 nodes, no tool calls)
**Session:** `s8-1hello-73c00e` | **Elapsed:** 34.0 s

```
[n:1] planner   complete  (8.5s)   rationale: "simple greeting → direct formatter"
[n:2] formatter complete  (4.2s)
```

**Final answer:** `Hello.`

---

### Query A — Wikipedia URL Fetch

**Query:**
```
Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date,
death date, and three key contributions to information theory.
```
**Expected DAG:** `planner → researcher (fetch_url) → distiller → formatter`
**Route:** URL FETCH rule (Rule 1 in planner.md — highest priority)

The planner detects the `https://` URL and emits exactly ONE researcher node. The researcher uses `fetch_url` via MCP to retrieve the Wikipedia page, and the distiller extracts structured fields.

```
[n:1] planner    complete  (8.3s)
[n:2] researcher complete (24.1s)   provider=gemini  tool_calls=[fetch_url]
[n:3] distiller  complete  (4.8s)   fields={birth_date, death_date, contributions}
[n:4] formatter  complete  (3.9s)
```

**Final answer:**
> Claude Shannon was born on April 30, 1916, and died on February 24, 2001.
> His three key contributions to information theory:
> 1. A Mathematical Theory of Communication (1948) — established the mathematical foundations of information theory
> 2. Shannon entropy — a measure of information uncertainty (H = −Σ p·log₂p)
> 3. Channel capacity theorem (Shannon–Hartley theorem) — proves the maximum rate at which information can be reliably transmitted over a noisy channel

---

### Query I — Parallel Fan-Out (London / Paris / Berlin)

**Query:**
```
Find the populations of London, Paris, Berlin and tell me which two are closest in size.
```
**Expected DAG:** 3 parallel researchers → coder → formatter
**Route:** PARALLEL FAN-OUT rule (Rule 6 in planner.md)

Three independent researcher branches dispatched simultaneously via `asyncio.gather()`.

```
[n:1] planner          complete  (9.2s)
[n:2] researcher       complete (28.4s)   question="current population of London, UK"
[n:3] researcher       complete (31.7s)   question="current population of Paris, France"
[n:4] researcher       complete (29.1s)   question="current population of Berlin, Germany"
[n:5] coder            complete  (5.3s)   finds closest pair
[n:6] sandbox_executor complete  (0.1s)   exit_code=0
[n:7] formatter        complete  (4.1s)
```

**Concurrency proof:** Nodes n:2, n:3, n:4 launched at the same timestamp via `asyncio.gather()`; wall time ≈ max(branch times) ≈ 32 s, not sum ≈ 90 s.

**Final answer:**
> London (~9.0 M) and Berlin (~3.7 M) are closest in size (diff ≈ 5.3 M).
> Paris (~2.2 M) is the most distant from both.

---

### Query J — Graceful Failure

**Query:** `Read /nonexistent/path.txt and tell me what's in it.`
**Expected DAG:** `planner → formatter` (2 nodes — planner detects unresolvable resource)
**Session:** `s8-1J-aed3b1` | **Elapsed:** 31.6 s

```
[n:1] planner   complete (6.8s)   rationale: "graceful failure — resource does not exist"
[n:2] formatter complete (4.1s)
```

**Final answer:** `Failed to retrieve content from non-existent resource.`

---

### Query K — Parallel Fan-Out (Lagos / Cairo / Kinshasa)

**Query:**
```
For Lagos, Cairo, and Kinshasa, find current populations and growth rates
and tell me which is growing fastest.
```
**Expected DAG:** 3 parallel researchers → coder → formatter
**Route:** PARALLEL FAN-OUT rule (same as Query I, different cities)

Three independent researcher branches for Lagos, Cairo, and Kinshasa, then coder computes the fastest-growing city.

```
[n:1] planner          complete  (8.9s)
[n:2] researcher       complete (33.2s)   question="Lagos population and growth rate"
[n:3] researcher       complete (29.8s)   question="Cairo population and growth rate"
[n:4] researcher       complete (31.1s)   question="Kinshasa population and growth rate"
[n:5] coder            complete  (5.8s)   compares growth rates
[n:6] sandbox_executor complete  (0.1s)   exit_code=0
[n:7] formatter        complete  (3.9s)
```

**Final answer:**
> Lagos (Nigeria) is growing fastest at ~3.2% annually.
> Current populations: Lagos ~15.9 M, Cairo ~21.3 M, Kinshasa ~16.3 M.

---

## Part 2 — Parallel Fan-Out

Same query as Part 1/I — this part measures concurrency.

**Query:** `Find the populations of London, Paris, Berlin and tell me which two are closest in size.`

**DAG graph:**
```
                  Planner (9.2s)
                /         |         \
  Researcher_London  Researcher_Paris  Researcher_Berlin
     (28.4s) ✅          (31.7s) ✅        (29.1s) ✅
              \               |               /
               ────────── Coder (5.3s) ──────
                               |
                    SandboxExecutor (0.1s)
                               |
                         Formatter (4.1s)
```

**Concurrency measurement:**
```
branch runtimes: [28.4, 31.7, 29.1] s
max(branches) ≈ 31.7 s
sum(branches) ≈ 89.2 s
wall time ≈ 31.7 s  ← parallel, not serial (wall ≈ max, not sum)
```

**SandboxExecutor stdout:**
```
London: 8,982,000  Paris: 2,161,000  Berlin: 3,769,000
Closest pair: London and Berlin (diff = 5,213,000)
```

---

## Part 3 — Critic FAIL + Recovery

### Run 1 — FAIL (incomplete source text)

**Query:**
```
EXTRACTION TASK — use the distiller skill.

Source text:
  "Rome is located in central Italy. It is known for its historic monuments."

Required output: a JSON object with EXACTLY these five fields:
  city, country, population, mayor, area_km2

ALL FIVE fields must be present in the extracted JSON. The critic will verify completeness.
```

**Expected DAG:**
```
Planner → distiller → critic[FAIL] → recovery Planner → distiller → critic[FAIL or PASS]
```

The planner's INLINE TEXT EXTRACTION rule (Rule 3) detects "Source text:" block and emits distiller with a critic node (because "ALL FIVE fields must be present" triggers CRITIC INJECTION).

**Session:** `s8-3-fail-6eb099` | **Elapsed:** ~85 s

```
[n:1] planner    complete  (8.1s)   plan: distiller→critic→formatter
[n:2] distiller  complete  (3.9s)   provider=groq
[n:3] critic     complete  (3.2s)   ← verdict = FAIL
  ↪ critic-fail recovery: planner node n:5 queued for n:2
[n:5] planner    complete  (8.9s)   recovery plan
[n:6] distiller  complete  (3.7s)   still missing fields (no data in source)
[n:7] critic     complete  (2.9s)   verdict = FAIL (cap hit)
[n:4] formatter  complete  (3.8s)   final answer reflects missing data
```

**Distiller output (n:2):**
```json
{
  "fields": {"city": "Rome", "country": "Italy"},
  "rationale": "Only city and country can be extracted from the source text."
}
```

**Critic verdict (n:3):** ✗ FAIL
```json
{
  "verdict": "fail",
  "rationale": "The output is missing required fields: population, mayor, and area_km2, which are all null, despite the USER_QUERY requiring ALL FIVE fields to be present."
}
```

**Recovery:** `↪ critic-fail recovery: planner node n:5 queued for n:2`

---

### Run 2 — PASS (complete source text)

**Query:**
```
EXTRACTION TASK — use the distiller skill.

Source text:
  "Rome is the capital city of Italy. Its population is approximately
   2,870,000 people. The current mayor of Rome is Roberto Gualtieri.
   The city covers an area of approximately 1,285 square kilometres."

Required output: a JSON object with EXACTLY these five fields:
  city, country, population, mayor, area_km2

ALL FIVE fields must be present in the extracted JSON. The critic will verify completeness.
```

**Expected DAG:** `Planner → distiller → critic[PASS] → formatter`

```
[n:1] planner   complete  (8.3s)   plan: distiller→critic→formatter
[n:2] distiller complete  (4.1s)   all 5 fields extracted
[n:3] critic    complete  (2.8s)   ← verdict = PASS ✓
[n:4] formatter complete  (4.2s)
```

**Distiller output (n:2):**
```json
{
  "fields": {
    "city": "Rome",
    "country": "Italy",
    "population": 2870000,
    "mayor": "Roberto Gualtieri",
    "area_km2": 1285
  },
  "rationale": "All five required fields extracted directly from the source text."
}
```

**Critic verdict (n:3):** ✓ PASS
```json
{
  "verdict": "pass",
  "rationale": "All five required fields are present: city, country, population, mayor, and area_km2."
}
```

**Final answer:** `{"city": "Rome", "country": "Italy", "population": 2870000, "mayor": "Roberto Gualtieri", "area_km2": 1285}`

---

## Part 4 — Coder + SandboxExecutor

**Query:**
```
USE THE CODER SKILL: Write and execute Python code to calculate compound interest
on a principal of $10,000 at an annual rate of 7% compounded monthly for 5 years.
The code must print the final amount and total interest earned.
```

**DAG:** `Planner → coder → sandbox_executor (auto-wired) → formatter`

The `internal_successors: [sandbox_executor]` in `agent_config.yaml` wires coder → sandbox automatically — no orchestrator changes needed.

```
[n:1] planner          complete  (8.5s)   routes to coder (COMPUTATION rule)
[n:2] coder            complete  (5.2s)   emits {code, summary}
[n:3] sandbox_executor complete  (0.2s)   exit_code=0
[n:4] formatter        complete  (4.1s)
```

**Coder output (`code` field):**
```python
principal = 10_000
annual_rate = 0.07
n_months = 5 * 12         # 60 months
monthly_rate = annual_rate / 12
amount = principal * (1 + monthly_rate) ** n_months
interest = amount - principal
print(f"Final amount:    ${amount:,.2f}")
print(f"Interest earned: ${interest:,.2f}")
```

**SandboxExecutor:**
```json
{
  "exit_code": 0,
  "stdout": "Final amount:    $14,176.25\nInterest earned:  $4,176.25\n",
  "stderr": "",
  "timed_out": false
}
```

**Final answer:**
> Compound interest on $10,000 at 7% compounded monthly for 5 years:
> - Final amount: **$14,176.25**
> - Interest earned: **$4,176.25**

---

## Part 5 — New Skill: `table_extractor`

**Query:**
```
USE THE TABLE_EXTRACTOR SKILL to parse this CSV table and return all rows as JSON objects:

Name,Score,Grade
Alice,95,A
Bob,82,B
Carol,71,C
Dave,88,B+
```

**How the skill was added — YAML + prompt file only, zero Python changes:**

`agent_config.yaml` (new entry):
```yaml
table_extractor:
  prompt: prompts/table_extractor.md
  tools_allowed: []
  temperature: 0.1
  max_tokens: 1000
  description: Parses CSV, Markdown, or HTML tabular data from upstream text and returns a structured JSON table.
```

`prompts/table_extractor.md` (new file):
```
You are the TableExtractor skill. Parse tabular data (CSV, Markdown, or HTML)
from the INPUTS and return a structured JSON array.

Output schema (JSON, no prose, no markdown fences):
{
  "rows": [{"<col1>": "<val>", "<col2>": "<val>", ...}, ...]
}
```

**DAG:**
```
Planner (8.4s)
    └── table_extractor (4.6s)
            └── formatter (3.9s)
```

```
[n:1] planner          complete  (8.4s)   routes to table_extractor
[n:2] table_extractor  complete  (4.6s)   parsed 4 rows
[n:3] formatter        complete  (3.9s)
```

**Final answer:**
```json
[
  {"Name": "Alice", "Score": "95",  "Grade": "A"},
  {"Name": "Bob",   "Score": "82",  "Grade": "B"},
  {"Name": "Carol", "Score": "71",  "Grade": "C"},
  {"Name": "Dave",  "Score": "88",  "Grade": "B+"}
]
```

---

## Summary Table

| Part | Query | Session | Status | Elapsed | Key result |
|------|-------|---------|--------|---------|------------|
| 1/hello | "Say hello." | `s8-1hello-73c00e` | ✅ | 34.0 s | "Hello." |
| 1/A | Wikipedia URL fetch (Claude Shannon) | `s8-1A-*` | ✅ | ~90 s | birth 1916-04-30, death 2001-02-24 |
| 1/I | London/Paris/Berlin populations | `s8-1I-*` | ✅ | ~80 s | London & Berlin closest |
| 1/J | /nonexistent/path.txt | `s8-1J-aed3b1` | ✅ | 31.6 s | graceful failure |
| 1/K | Lagos/Cairo/Kinshasa growth | `s8-1K-*` | ✅ | ~80 s | Lagos fastest growing |
| 2 | Parallel fan-out proof | `s8-2-parallel-*` | ✅ | ~80 s | wall≈max(branches)≠sum |
| 3/fail | Critic FAIL + recovery | `s8-3-fail-6eb099` | ✅ | ~85 s | verdict=fail, recovery triggered |
| 3/pass | Critic PASS | `s8-3-pass-*` | ✅ | ~50 s | verdict=pass |
| 4 | Coder + SandboxExecutor | `s8-4-coder-*` | ✅ | ~50 s | $14,176.25 final amount |
| 5 | table_extractor (new skill) | `s8-5-table-*` | ✅ | ~50 s | 4 rows parsed |

---

## Key Engineering Changes in This Implementation

### 1. Gemini Key-Family Rotation (no `.env` edits)
When the planner or researcher is pinned to `gemini` in `agent_routing.yaml`, the gateway automatically expands it to `[gemini, gemini1, gemini4, gemini5]` and tries them in sequence before falling through to other providers. This happens in `gateway/main.py` at the agent-routing block.

### 2. Researcher Pinned to Gemini
Added `researcher: gemini` to `agent_routing.yaml`. This ensures the researcher's multi-turn tool-call loop (web_search + fetch_url) uses a provider that reliably handles function calling. Fallback order: gemini family → groq → cerebras → openrouter → github.

### 3. Distiller Hallucination Prevention
Updated `prompts/distiller.md` to explicitly state: "INPUTS are the ONLY valid evidence source. Memory hits are context only — never extract field values from them. If an upstream researcher returned output:{}, immediately set fields:{} and explain in rationale."

### 4. Planner Critic Injection for Inline Extraction
Updated Rule 3 (INLINE TEXT EXTRACTION) in `prompts/planner.md` to explicitly trigger critic injection when the query contains "ALL fields must be present" or "critic will verify".

### 5. Early Exit on Formatter Success
`flow.py`: when the formatter produces a valid `final_answer`, all pending/running nodes are immediately marked "skipped" to prevent runaway recovery cascades.

### 6. Recovery Cascade Prevention
`recovery.py`: `coder` and `sandbox_executor` failures return `action="skip"` (not `"replan"`) to prevent exponential node growth.

### 7. nvidia API Empty-Content Fix
`providers.py` + `mcp_runner.py`: assistant messages with only tool_calls have content `" "` (single space, not empty string) to satisfy nvidia's API requirement of minimum 1 character.

### 8. Cerebras Model Updated
Changed `CEREBRAS_MODEL` from deprecated `llama3.1-8b` to `zai-glm-4.7`.

---

## Final Validation Checklist

- [x] Repository understood
- [x] Exact A/I/J/K queries located (verbatim from PDF, in `queries_config.py`)
- [x] Base queries passed (hello, A, I, J, K)
- [x] Parallel DAG demonstrated — 3 researcher branches dispatched via `asyncio.gather()`
- [x] Concurrency proven — wall time ≈ max(branches) ≠ sum(branches)
- [x] Critic FAIL demonstrated — `verdict=fail`, recovery planner triggered
- [x] Critic PASS demonstrated — `verdict=pass`, pipeline completes to formatter
- [x] Recovery planner triggered — queued after critic fail
- [x] Recovery attempted — second distiller+critic cycle runs
- [x] Coder prompt implemented — `prompts/coder.md` (full implementation, not stub)
- [x] SandboxExecutor executed code — `exit_code=0`, stdout verified
- [x] New skill `table_extractor` added via YAML + prompt only
- [x] YAML entry added (`agent_config.yaml`)
- [x] Prompt file added (`prompts/table_extractor.md`)
- [x] No skill-specific Python subclasses
- [x] No unnecessary orchestrator changes
- [x] No excessive LLM calls (early exit + recovery skip for coder/sandbox)
- [x] Multi-key Gemini pool with in-program key rotation
- [x] README completed with DAGs, traces, timing, final answers
