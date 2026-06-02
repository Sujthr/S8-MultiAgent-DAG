"""
Assignment query definitions — verbatim from the Session 8 PDF.

Sources:
  PDF page 29-31 (Worked queries section):
    hello — "Say hello."
    A     — Fetch Claude Shannon Wikipedia page (birth/death dates, 3 contributions)
    I     — London, Paris, Berlin populations (parallel fan-out)
    J     — Read /nonexistent/path.txt (graceful failure)
    K     — Lagos, Cairo, Kinshasa populations + growth rates (resumable execution)

  Assignment parts 3-5 use SEPARATE queries designed to exercise
  those specific mechanisms; they are NOT the same as the base queries.
"""

# ── Part 1 Base Queries (verbatim from PDF) ───────────────────────────────────

QUERY_HELLO = "Say hello."

# Query A — S7 carryover: Wikipedia fetch + distiller extraction
QUERY_A = (
    "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his "
    "birth date, death date, and three key contributions to information theory."
)

# Query I — parallel fan-out: three independent researcher branches
# Verbatim from PDF page 11: "The query is verbatim: Find the populations of
# London, Paris, Berlin and tell me which two are closest in size."
QUERY_I = (
    "Find the populations of London, Paris, Berlin and tell me which two "
    "are closest in size."
)

# Query J — graceful failure: planner recognises unanswerable query
QUERY_J = "Read /nonexistent/path.txt and tell me what's in it."

# Query K — resumable execution: parallel researchers + SIGKILL+resume demo
QUERY_K = (
    "For Lagos, Cairo, and Kinshasa, find current populations and growth "
    "rates and tell me which is growing fastest."
)

# ── Part 2 Parallel Fan-out ───────────────────────────────────────────────────
QUERY_PARALLEL = QUERY_I   # same query — Part 2 is the parallel-timing proof

# ── Part 3 Critic Demo ────────────────────────────────────────────────────────
# These are SEPARATE demonstration queries (not base queries).
# Both use distiller so the critic is auto-inserted (critic: true in YAML).
# FAIL: source text is missing three of the five required fields → critic rejects
# PASS: source text contains all five required fields → critic approves

QUERY_CRITIC_FAIL = (
    "EXTRACTION TASK — use the distiller skill.\n\n"
    "Source text:\n"
    '  "The Colosseum is Rome\'s most famous ancient amphitheatre, '
    'built in the first century AD."\n\n'
    "Required output: a JSON object with EXACTLY these five fields:\n"
    "  city, country, population, mayor, area_km2\n\n"
    "ALL FIVE fields must have non-null, substantive values. "
    "The critic will verify that all five fields are present and non-null."
)

QUERY_CRITIC_PASS = (
    "EXTRACTION TASK — use the distiller skill.\n\n"
    "Source text:\n"
    '  "Rome is the capital city of Italy. Its population is approximately '
    "2,870,000 people. The current mayor of Rome is Roberto Gualtieri. "
    'The city covers an area of approximately 1,285 square kilometres."\n\n'
    "Required output: a JSON object with EXACTLY these five fields:\n"
    "  city, country, population, mayor, area_km2\n\n"
    "ALL FIVE fields must be present in the extracted JSON. "
    "The critic will verify completeness."
)

# ── Part 4 Coder + SandboxExecutor ───────────────────────────────────────────
# Explicit instruction to use the coder skill so the planner does not
# fall back to retriever.  SandboxExecutor wires in automatically via
# internal_successors in agent_config.yaml.
QUERY_CODER = (
    "USE THE CODER SKILL: Write and execute Python code to calculate "
    "compound interest on a principal of $10,000 at an annual rate of 7% "
    "compounded monthly for 5 years. "
    "The code must print the final amount and total interest earned."
)

# ── Part 5 New Skill (table_extractor) ───────────────────────────────────────
# Explicit instruction so the planner routes to table_extractor, not distiller.
QUERY_NEW_SKILL = (
    "USE THE TABLE_EXTRACTOR SKILL to parse this CSV table and return all "
    "rows as JSON objects:\n\n"
    "Name,Score,Grade\n"
    "Alice,95,A\n"
    "Bob,82,B\n"
    "Carol,71,C\n"
    "Dave,88,B+"
)
