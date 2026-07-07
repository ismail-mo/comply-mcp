# COMPLY — Master Refactoring Specification

**A deterministic Eurocode compliance auditor with a thin AI membrane.**

This document is the complete build specification. It captures every architectural decision, tool definition, skill contract, output format, citation rule, formula strategy, UI theme, and worked example finalised for this project. Read it in full before writing any code. It is long by design — everything you need is here so you never have to guess.

> **⚠ Illustrative examples — format and voice only, not ground truth.** The
> worked audit numbers throughout this document are hand-drafted illustrations of
> layout, structure, and voice. They were written at different times and are
> deliberately NOT all internally consistent — for example: the overview in 6.4
> counts eight findings while the table in 7.4 lists ten; the quick_answer example
> in 3.2 describes an "upsize" that actually lowers the area (168.1 → 149.8 cm²);
> the steel-grade / fy figures differ between 3.2 and 6.6. This is expected and
> intentional. In the built product EVERY number is produced by the deterministic
> engine and is never copied from these examples. **Reproduce the format and
> voice; never reproduce these specific numbers as fact.**

---

# PART 1 — THE GOVERNING PHILOSOPHY

## 1.1 What This Product Is

COMPLY reads a structural engineering design report (PDF), checks every quantitative claim against the relevant Eurocode clause, and returns a structured audit trail with verdicts, evidence, calculated deltas, and recommended actions. What takes an engineer days of manual cross-referencing takes seconds.

The differentiator versus competitors (Civils.ai and similar) is **formula-verified checks with calculated deltas and exact clause citations** — not just contract/spec keyword search, but genuine Eurocode formula verification producing pass/fail with the actual numbers.

## 1.2 The One Principle That Governs Everything

```
Push every decision to the lowest-intelligence layer
that can make it correctly.

Regex/parse   before   LLM extraction
Lookup table  before   computation
Pure function before   LLM reasoning
Cache         before   recompute
LLM           only for language and genuine ambiguity
```

The AI is the most expensive, slowest, least reliable, and least verifiable component in the stack. It earns its place only where nothing cheaper works. Everything that can be deterministic Python **must** be deterministic Python.

## 1.3 The Critical Reframe

This is not "an AI system with some code." It is **a deterministic engineering-checking engine wrapped in a thin AI membrane**. The AI touches only the edges:

```
AI TOUCHES (language + genuine ambiguity only)
──────────────────────────────────────────────
- extract values from messy calc prose   [1 call/element]
- classify ambiguous element type          [rare]
- write the overview paragraph             [1 call/audit]
- retrieve clause prose for Q&A            [quick_answer only]

AI NEVER TOUCHES (deterministic, tested code)
──────────────────────────────────────────────
- running any formula
- deciding any pass/fail
- assigning any status
- comparing any values
- the check registry
- caching
- session state
```

The old design had the AI running formulas and deciding pass/fail. **That is backwards and is a correctness and liability bug, not a tuning issue.** The AI does language work. Deterministic code does engineering work.

## 1.4 Runtime Targets

```
                    OLD DESIGN       TARGET
────────────────────────────────────────────────────────
LLM calls/element   ~14              2
First check         ~9 minutes       ~10-15 s
Repeat (cached)     ~9 minutes       ~1-2 s
Full document       n/a              ~15-60 s (API concurrency bound)
Context per audit   5,000+ tokens    ~640 tokens (flat)
TPM limit hits      frequent         never
```

The engine (40+ formula functions running on extracted numbers) is sub-100ms and will **never** be the bottleneck. The two AI calls are ~95% of runtime. Optimise call count, not context — though we do both.

---

# PART 2 — TOOLS (exactly THREE)

Cut from sixteen to three. Only jobs that genuinely require the AI's language ability survive as tools. Everything else became deterministic Python (see Part 4).

## 2.1 Tool: `extract_element`

The single hard AI job — turning messy human-written calc prose into structured values.

```
PURPOSE
Takes the raw PDF pages for ONE element and returns
strict, schema-enforced JSON of all its design values.

INPUT
{
  element_type: "column",
  pages:        [14, 15, 16],       // from document index
  required_inputs: ["NEd","A","iz","Le","fy","Gk","Qk","VEd"]
                                     // union of all inputs
                                     // needed by this element's
                                     // registered checks
}

OUTPUT (schema-enforced — model CANNOT return prose)
{
  element:      "column",
  designation:  "UC 254x254x132",
  values: {
    NEd: { value: 6896.25, unit: "kN", page: 15,
           quote: "Total Axial Load = 6896.25",
           confidence: 0.98, flag: null },
    Le:  { value: 3.22, unit: "m", page: 9,
           quote: "Le = 0.7 x 4.6 = 3.22 m",
           confidence: 0.96, flag: "ASSUMED",
           note: "effective length assumed fixed-pinned,
                  base connection not detailed" },
    fy:  { value: 275, unit: "N/mm2", page: 8,
           quote: "grade S275", confidence: 0.72,
           flag: "ASSUMED",
           note: "grade stated, thickness band not
                  verified against EN 10025-2" }
  },
  not_found: ["VEd"]     // EXPLICIT — deterministically
                         // drives MISSING rows
}

CRITICAL RULES
- Output MUST be schema-enforced (tool use / structured
  output). If invalid JSON is returned, the call fails
  and retries. Never parse the model's prose answer.
- Every value carries: value, unit, page, source quote,
  confidence, and assumption flag.
- not_found is MANDATORY and explicit. Absence is data.
- Only extract values explicitly stated. Never infer or
  calculate a value. If it isn't in the pages, it goes
  in not_found.
- Feed ONLY the element's pages, never the whole PDF —
  extraction latency scales with input size.
```

## 2.2 Tool: `write_overview`

Language only. Cannot alter any verdict.

```
PURPOSE
Takes the FINISHED deterministic findings array and
writes the overview paragraph and recommended actions
in house style.

INPUT
{
  element:  "column",
  designation: "UC 254x254x132",
  document: "d3-solution.pdf",
  findings: [ ...complete verdicts from the engine ]
}

OUTPUT
{
  overview: "This audit checked the base-level steel
             column in...",           // full paragraph
  recommended_actions: [
    "Upsize column section — NEd = 6,896 kN exceeds
     Nb,Rd = 4,059 kN. Try UC 305 x 305 x 118 or larger.",
    ...
  ]
}

ABSOLUTE RULE
This tool CANNOT change any verdict, ratio, status, or
number. The findings are locked by the deterministic
engine BEFORE this runs. It narrates results; it does
not produce them. See Part 6 for exact writing style.
```

## 2.3 Tool: `search_documents`

Free-form semantic retrieval, only for the quick_answer path.

```
PURPOSE
Retrieves Eurocode clause PROSE so quick_answer can
quote it. Genuinely needs retrieval + language, so it
stays a tool.

INPUT
{ query: "what does clause 6.3.1 say", top_k: 3 }

OUTPUT
{
  query: "...",
  results: [
    { clause: "Eurocode 3, Section 6.3.1",
      text: "...", page: 47, chunk_id: "eurocode3-47" }
  ]
}

READS FROM
Firestore code_chunks (embedded Eurocode prose).
This is the ONLY feature that uses the vector store.
```

## 2.4 Tools That Were DELETED (now deterministic Python)

```
formula_runner            -> formulas/*.py pure functions
result_comparator         -> classify() in the engine
check_registry_lookup     -> CHECK_REGISTRY dict read
national_annex_checker    -> national_annex lookup table
cross_reference_checker   -> cross_reference() in the engine
compare_value_to_clause   -> dead, replaced by classify()
extract_design_values     -> dead, replaced by extract_element
section_property_lookup   -> regex + cached fetch on upload
cache_hit_checker         -> Python cache check in backend
context_compressor        -> not needed (state in Redis)
render_audit_output       -> frontend renders JSON
document_indexer          -> PyMuPDF parse step on upload
element_classifier        -> string match on index (AI only
                            for genuinely ambiguous cases)
```

---

# PART 3 — SKILLS (exactly THREE)

All three are **format contracts**. They shape what the model outputs. **They do not orchestrate, fire tools, run in parallel, or monitor anything** — that logic lives in backend Python. A skill is markdown that shapes model behaviour, nothing more.

## 3.1 Skill: `compliance_audit`

The full audit output contract. This is the format bible. Full definition of structure and style is in Part 6 and Part 7. Summary:

```markdown
# Compliance Audit Skill

## Trigger
A request to check, audit, or flag compliance on a
structural element. Phrases like "check the column",
"run a beam check", "audit the primary beam against
Eurocode 3", "flag all violations in the column design",
"check 610 x 178 x 100 UB for compliance".

## Output structure (in order, always)
1. Title block
2. Summary pills (coloured, one line, count per status)
3. Overview (full-sentence paragraph)
4. Recommended actions (2-4 arrow bullets)
5. Findings table (5 columns: status/category/issue/
   reference/action)
6. Calculation summary (collapsible, appended)

## Does NOT
- Orchestrate tools. The backend runs the engine and
  the two AI tools. This skill governs the FORMAT of
  the final rendered output only.
```

## 3.2 Skill: `quick_answer`

The short-answer contract, for direct questions rather than full audits.

```markdown
# Quick Answer Skill

## Trigger
A direct question about a value, section, clause, or
fix. Not a compliance check request. Phrases like
"what is a better section size", "what does clause
6.3.1 say", "why did the column fail", "what is chi",
"how do I fix the buckling check".

## Output rules
- Full sentences with full words, in the style of the
  overview section, BUT including quantities and for
  the purpose of suggesting actions.
- NOT 5 short clipped sentences — flowing prose that
  reads professionally.
- Include the specific value or answer, with units.
- Two long comma-separated sentences is the target
  shape when suggesting a fix.
- Cite the clause if relevant. On isolated questions
  the clickable coloured citation badge MAY be surfaced
  ("call the citation clause on isolated questions").
- No table, no overview block, no title block, no
  summary pills.
- If the answer genuinely requires a full check to be
  run, redirect to the compliance_audit skill instead.

## Worked example — "what is a better section size"
"The most straightforward path forward would be to
upsize the column section to a UC 305 x 305 x 118, as
this increases the cross-sectional area from 168.1 cm2
to 149.8 cm2 and raises the minor axis radius of
gyration from iz = 6.69 cm to iz = 7.69 cm, which
together reduce the non-dimensional slenderness from
lam_bar = 0.513 down to lam_bar = 0.419 and raise the
buckling reduction factor from chi = 0.878 to
chi = 0.921. It is also worth confirming the steel grade
against the actual section order before finalising the
section choice, as switching from the assumed S275 to a
confirmed S355 would raise fy from 275 N/mm2 to
355 N/mm2 and increase the squash load Npl,Rd from
4,623 kN to approximately 5,966 kN, which combined with
the higher chi from the upsized section would bring
Nb,Rd well above the design axial load of NEd = 6,896 kN
and put the column in a position to pass the buckling
limit comfortably."
```

> *Illustrative (see top-of-document note): the numbers above show the voice and
> shape of a quick_answer only and are not internally consistent — the "upsize"
> lowers the area yet is described as an increase. The engine supplies real values.*

## 3.3 Skill: `calculation_summary`

```markdown
# Calculation Summary Skill

## Purpose
Appends a collapsible calculation summary to the bottom
of any compliance_audit output. Documents the full
working behind every finding in the table.

## Trigger
Automatically appended at the end of compliance_audit
output. Never triggered directly by a user prompt.
(Exception: if a user explicitly asks "show me the
working for the buckling check" with no prior audit in
context, the backend runs the engine first to populate
the values, then this skill renders them.)

## Input contract (read from CONTEXT, not fresh tool calls)
By the time this runs, the deterministic engine has
already computed everything and it sits in context /
session state:
- input values with units, source page, source quote
- all intermediate formula steps for each check
- final result, verdict, delta for each check

## Output contract
One collapsible block per check that ran.
Closed by default.
Label shows: "Calculation summary — N lines"
Expanded view shows full working in bordered monospace
block.

## Structure per check block
[v Check name — Calculation summary — N lines]
+--------------------------------------------+
|                                            |
|  Input values                              |
|  ---------------------------------------   |
|  [parameter] = [value] [unit]              |
|  source: [document.pdf . p.N]              |
|                                            |
|  Formula                                   |
|  [step 1 = result]                         |
|  [step 2 = result]                         |
|  ...                                       |
|                                            |
|  Result                                    |
|  [Ed] / [Rd] = [ratio] [op] 1.0  [PASS/FAIL]|
|                                            |
+--------------------------------------------+

## Rules
- One block per check in the findings table
- Order matches the findings table row order
- All values include units
- All source references include page number
- Formula steps match the engine output exactly —
  never paraphrase or simplify
- Result line always shows the ratio and the limit
  (> 1.0 or <= 1.0)
- Section property values cite Steel Blue Book as
  source, not the PDF
- Web-fetched values flagged with:
  "> Steel Blue Book . [section] . [URL]"

## Worked example — the finalised buckling block
[v Flexural buckling — Calculation summary — 14 lines ]
+------------------------------------------------------+
|                                                      |
|  Input values                                        |
|  -------------------------------------------------   |
|  NEd  = 6,896.25 kN   > column_check_4.pdf . p.1     |
|  A    = 168.1 cm2     > Steel Blue Book . UC254x132  |
|  iz   = 6.69 cm       > Steel Blue Book . UC254x132  |
|  fy   = 275 N/mm2     > EN 10025-2 . tf = 25.3 mm    |
|  Le   = 0.7 x 4.6     = 3.22 m                       |
|  gM1  = 1.0                                          |
|                                                      |
|  Formula — Eurocode 3, Section 6.3.1                 |
|  Npl,Rd = (168.1 x 100 x 275) / 1.0 = 4,622.75 kN    |
|  lam    = 3.22 / 0.0669             = 48.13          |
|  lam_bar= 48.13 / 93.9              = 0.513          |
|  phi    = 0.5[1+0.34(0.513-0.2)+0.513^2] = 0.685     |
|  chi    = 1/[0.685+sqrt(0.685^2-0.513^2)] = 0.878    |
|  Nb,Rd  = 0.878 x 4,622.75          = 4,059.17 kN    |
|                                                      |
|  Result                                              |
|  NEd / Nb,Rd = 6,896.25 / 4,059.17 = 1.70 > 1.0      |
|  X  FAIL — exceeds buckling limit by 70%             |
|                                                      |
+------------------------------------------------------+
```

## 3.4 Skills That Were DELETED

```
batch_check, prefetch_properties, context_compressor,
document_indexer, progressive_renderer, cache_hit_checker,
on_upload, prefetch_clauses, pre_extract_values,
pre_run_formulas

These were "skills that orchestrate" — an impossible
concept. Skills cannot fire tools, run in parallel, or
monitor thresholds. All of this is backend FastAPI
orchestration code, NOT SKILL.md files.
```

---

# PART 4 — THE DETERMINISTIC ENGINE (backend Python, NOT tools, NOT AI)

This is the heart of the product. Pure Python. No network, no LLM, no Firestore in the compute path. Given inputs, it produces the entire audit result deterministically and is fully unit-tested.

## 4.1 Directory Structure

```
vc-MCP-APP-2/
+-- reference/                 <- BUILD-TIME ONLY, gitignored
|   +-- eurocode3.pdf            (copyright — never commit)
|   +-- worked_examples.pdf
|   +-- blue_book_extract.pdf
|   +-- coursework/
|       +-- column_check_8.pdf
|       +-- beam_checks.pdf
|
+-- formulas/                  <- COMMITTED — pure functions
|   +-- flexural_buckling.py
|   +-- bending.py
|   +-- shear.py
|   +-- ltb.py
|   +-- compression.py
|   +-- deflection.py
|   +-- load_combo.py
|
+-- tables/                    <- COMMITTED — you transcribe these
|   +-- buckling_curves.py       (from EC3 Table 6.2)
|   +-- imperfection.py          (from EC3 Table 6.1)
|   +-- partial_factors.py       (from UK NA)
|
+-- tests/                     <- COMMITTED — known-answer tests
|   +-- test_flexural_buckling.py
|   +-- test_bending.py
|   +-- test_shear.py
|
+-- registries/                <- COMMITTED
|   +-- check_registry.py
|   +-- national_annex.py
|
+-- engine/                    <- COMMITTED — the orchestrator
|   +-- run_audit.py
|   +-- classify.py
|   +-- cross_reference.py
|
+-- mcp/                       <- MCP server (Python, FastMCP)
|   +-- server.py                (3 tools: extract_element,
|                                 write_overview, search_documents)
|
+-- skills/
    +-- compliance_audit/SKILL.md
    +-- quick_answer/SKILL.md
    +-- calculation_summary/SKILL.md
```

## 4.2 Separate Formula Logic From Lookup Data

The single most important engineering rule. A formula is a short pure function. The tables it depends on are separate data files. **Never hardcode a lookup value inside a formula** — that is where wrong answers hide.

```python
# tables/buckling_curves.py — pure DATA, no logic
# Transcribed from EC3 Table 6.2 — verify against printed standard
BUCKLING_CURVE = {
    ("UB", "major"): "a",
    ("UB", "minor"): "b",
    ("UC", "major"): "b",
    ("UC", "minor"): "c",
    # ... complete from EC3 Table 6.2
}

# tables/imperfection.py — from EC3 Table 6.1
IMPERFECTION_FACTOR = {
    "a0": 0.13, "a": 0.21, "b": 0.34,
    "c":  0.49, "d": 0.76
}
```

```python
# formulas/flexural_buckling.py — pure LOGIC, reads tables
from tables.buckling_curves import BUCKLING_CURVE
from tables.imperfection import IMPERFECTION_FACTOR

def flexural_buckling(NEd, A, iz, Le, fy,
                      section_type, axis, gamma_M1=1.0):
    curve   = BUCKLING_CURVE[(section_type, axis)]
    alpha   = IMPERFECTION_FACTOR[curve]
    Npl_Rd  = A * fy / gamma_M1
    lam     = Le / iz
    lam_1   = 93.9 * (235 / fy) ** 0.5
    lam_bar = lam / lam_1
    phi     = 0.5 * (1 + alpha * (lam_bar - 0.2) + lam_bar ** 2)
    chi     = min(1.0, 1 / (phi + (phi ** 2 - lam_bar ** 2) ** 0.5))
    Nb_Rd   = chi * Npl_Rd
    return {
        "result":  Nb_Rd,
        "unit":    "kN",
        "chi":     chi,
        "lam_bar": lam_bar,
        "steps": [
            f"Npl,Rd = ({A} x 100 x {fy}) / {gamma_M1} = {Npl_Rd:.2f} kN",
            f"lam = {Le} / {iz/100} = {lam:.2f}",
            f"lam_bar = {lam:.2f} / {lam_1:.1f} = {lam_bar:.3f}",
            f"curve {curve} -> alpha = {alpha}",
            f"phi = 0.5[1+{alpha}({lam_bar:.3f}-0.2)+{lam_bar:.3f}^2] = {phi:.3f}",
            f"chi = 1/[{phi:.3f}+sqrt({phi:.3f}^2-{lam_bar:.3f}^2)] = {chi:.3f}",
            f"Nb,Rd = {chi:.3f} x {Npl_Rd:.2f} = {Nb_Rd:.2f} kN"
        ],
        "governing": "NEd / Nb,Rd <= 1.0"
    }
```

Now the logic is ~12 lines and the tables are auditable data anyone can check against the printed code.

## 4.3 One Shared Formula Contract

Every formula takes a dict and returns the same shape. This is what lets the engine loop over 40+ formulas without special-casing any.

```python
# Every formula obeys this contract:
def any_formula(**inputs) -> dict:
    return {
        "result":    float,        # the resistance value
        "unit":      str,
        "steps":     list[str],    # for the calculation summary
        "governing": str           # the limit that applies
    }

# The engine registers them by id and never knows which
# one it's calling:
FORMULAS = {
    "flexural_buckling": flexural_buckling,
    "bending":           bending,
    "shear":             shear,
    "ltb":               lateral_torsional_buckling,
    "compression":       compression,
    "deflection":        deflection,
    "load_combo":        load_combo,
}
result = FORMULAS[check.formula_id](**inputs)   # uniform call
```

**Adding a formula = write one function to the contract + register one line. The engine, tools, and output never change.** This is the scaling mechanism.

## 4.4 The Check Registry (a dict, NOT a tool)

Static data read by `run_audit()`. Never called by the LLM. This is what deterministically produces MISSING rows — the engine loops over the complete required set and anything whose inputs are absent becomes MISSING.

```python
# registries/check_registry.py
CHECK_REGISTRY = {
    "column": [
        {"id": "compression",   "clause": "Eurocode 3, Section 6.2.4",
         "formula": "compression",  "inputs": ["NEd","A","fy"],
         "limit": "NEd / Nc,Rd <= 1.0",  "missing_status": "MISSING"},
        {"id": "flex_buckling", "clause": "Eurocode 3, Section 6.3.1",
         "formula": "flexural_buckling",
         "inputs": ["NEd","A","iz","Le","fy","section_type","axis"],
         "limit": "NEd / Nb,Rd <= 1.0",  "missing_status": "MISSING"},
        {"id": "section_class", "clause": "Eurocode 3, Section 5.5",
         "formula": "section_class", "inputs": ["tf","tw","fy"],
         "limit": "qualitative",  "missing_status": "WARNING"},
        {"id": "load_combo",    "clause": "EN 1990, Section A1.3",
         "formula": "load_combo",  "inputs": ["Gk","Qk"],
         "limit": "1.35Gk + 1.50Qk",  "missing_status": "MISSING"},
        {"id": "steel_grade",   "clause": "EN 10025-2",
         "formula": "steel_grade",  "inputs": ["tf","grade"],
         "limit": "qualitative",  "missing_status": "ASSUMED"},
        {"id": "shear",         "clause": "Eurocode 3, Section 6.2.6",
         "formula": "shear",  "inputs": ["VEd","Av","fy"],
         "limit": "VEd / Vpl,Rd <= 1.0",  "missing_status": "MISSING"},
    ],
    "beam": [
        {"id": "bending",     "clause": "Eurocode 3, Section 6.2.5",
         "formula": "bending",  "inputs": ["MEd","Wpl_y","fy"],
         "limit": "MEd / Mc,Rd <= 1.0",  "missing_status": "MISSING"},
        {"id": "shear",       "clause": "Eurocode 3, Section 6.2.6",
         "formula": "shear",  "inputs": ["VEd","Av","fy"],
         "limit": "VEd / Vpl,Rd <= 1.0",  "missing_status": "MISSING"},
        {"id": "ltb",         "clause": "Eurocode 3, Section 6.3.2",
         "formula": "ltb",  "inputs": ["MEd","Lcr","Wpl_y","fy"],
         "limit": "MEd / Mb,Rd <= 1.0",  "missing_status": "MISSING"},
        {"id": "deflection",  "clause": "Eurocode 3, Section 7.2.1",
         "formula": "deflection",  "inputs": ["L","EI","w"],
         "limit": "delta <= L/360",  "missing_status": "MISSING"},
        {"id": "section_class","clause": "Eurocode 3, Section 5.5",
         "formula": "section_class",  "inputs": ["tf","tw","fy"],
         "limit": "qualitative",  "missing_status": "WARNING"},
        {"id": "load_combo",  "clause": "EN 1990, Section A1.3",
         "formula": "load_combo",  "inputs": ["Gk","Qk"],
         "limit": "1.35Gk + 1.50Qk",  "missing_status": "MISSING"},
    ],
    # connection, slab, foundation added in later tiers
}
```

Only reference formulas that actually exist. A tier is defined by which formula functions you have written and tested — the registry only lists those.

## 4.5 The Engine — `run_audit()`

```python
# engine/run_audit.py
from registries.check_registry import CHECK_REGISTRY
from registries.national_annex import check_national_annex
from engine.classify import classify
from engine.cross_reference import cross_reference
from formulas import FORMULAS

def run_audit(element_type, extracted_values, section_props):
    registry = CHECK_REGISTRY[element_type]   # dict read, not a tool
    findings = []

    for check in registry:
        inputs = gather(check["inputs"], extracted_values, section_props)

        # MISSING — a required input is absent from the PDF
        if any(name in extracted_values["not_found"]
               for name in check["inputs"]):
            findings.append(build_missing(check, extracted_values))
            continue

        # ASSUMED — an input is flagged unverified
        assumed = [n for n in check["inputs"]
                   if extracted_values["values"].get(n, {}).get("flag") == "ASSUMED"]

        # qualitative clause with no number -> WARNING
        if check["limit"] == "qualitative":
            findings.append(build_warning(check, extracted_values))
            continue

        # DETERMINISTIC COMPUTE — pure function, no AI
        computed = FORMULAS[check["formula"]](**inputs)
        engineer = extracted_values["values"].get(check["id"] + "_result")

        status = classify(computed, engineer, check["limit"])

        na = check_national_annex(check, inputs)   # dict lookup

        findings.append(build_finding(check, computed, engineer,
                                      status, assumed, na))

    # CONFLICT — inter-element consistency (e.g. S275 vs S355)
    findings += cross_reference(findings, extracted_values)

    return findings
```

## 4.6 The `classify()` Function — Status Assignment

Deterministic branches over numbers. This is where the entire status taxonomy lives.

```python
# engine/classify.py
def classify(computed, engineer_value, limit, tolerance=0.02):
    # ERROR — engineer's number differs from the correct formula
    if engineer_value is not None:
        if abs(computed["result"] - engineer_value) / computed["result"] > tolerance:
            return {
                "status": "ERROR",
                "computed": computed["result"],
                "engineer": engineer_value,
                "discrepancy_pct": round(
                    abs(computed["result"] - engineer_value)
                    / computed["result"] * 100, 1)
            }

    # FAIL / PASS — deterministic comparison against the limit
    ratio = compute_ratio(computed, limit)   # Ed / Rd
    if ratio > 1.0:
        return {"status": "FAIL", "ratio": round(ratio, 2),
                "delta": compute_delta(computed, limit)}
    return {"status": "PASS", "ratio": round(ratio, 2)}
```

Full taxonomy the engine assigns:

```
FAIL       Ed > Rd, a number proves the clause is breached
ERROR      computed != engineer > 2%, or wrong partial factor,
           wrong sign, unreferenced value
MISSING    a required input absent -> check never performed
ASSUMED    an input flagged unverified, result depends on it
WARNING    qualitative clause, no number can satisfy it,
           engineer judgement required
PASS       Ed <= Rd, a number proves the clause is satisfied
CONFLICT   two element values disagree (cross_reference)
```

## 4.7 The Validation Suite — THE Liability Firewall

**This is non-negotiable and is what earns a trustworthy product.** Every formula ships with hand-worked known-answer tests before it is allowed to run. Your own coursework is the fixture library.

```python
# tests/test_flexural_buckling.py
from formulas.flexural_buckling import flexural_buckling

def test_column_check_8_known_fail():
    # from d3-solution coursework, hand-verified
    r = flexural_buckling(
        NEd=6896.25, A=168.1, iz=6.69, Le=3.22,
        fy=275, section_type="UC", axis="minor"
    )
    assert round(r["result"], 1) == 4059.2   # hand answer
    assert round(r["chi"], 3)    == 0.878     # hand answer

def test_second_known_pass():
    # a DIFFERENT hand-worked example — proves it generalises
    # one passing test can be a fluke; two independent
    # answers prove the function is correct
    ...
```

```
THE RULE
A formula does not go live until it reproduces a
hand-worked answer to 3 significant figures.
CI blocks any deploy where a known-answer test fails.

Sources of known answers:
- Your coursework (Check 8: chi=0.878, Nb,Rd=4059 kN, etc.)
- Steel Blue Book published resistances (dozens of free
  validation cases — your function must match the
  published Nb,Rd for a standard section)
- Textbook worked examples (SCI, Designer's Guide to EC3)
```

---

# PART 5 — FIRESTORE & STATE

## 5.1 Firestore Usage — Edges Only

```
STORES (touched only on upload / cache / persist,
        NEVER in the per-check hot path,
        NEVER called by the LLM):

section_cache/    Steel Blue Book properties, keyed by
                  designation. Fetched once (web_fetch),
                  cached forever.
                  { "UC 254x254x132": {A, iz, Wpl_y, Av,
                    tf, tw, source, url} }

formula_cache/    Computed results, keyed PER CHECK on its
                  specific inputs — NOT whole-document hash.
                  key = hash(check_id + relevant_input_values)
                  Change one value -> only checks using it
                  invalidate; everything else stays cached.

document_index/   Parsed PDF structure, keyed by doc hash.
                  Re-opening a document skips re-parsing.

code_chunks/      Eurocode PROSE, embedded — ONLY powers
                  search_documents / quick_answer. The engine
                  never touches it.

audits/           Completed audit records, keyed by
                  firm/project/audit_id. Enables history and
                  version-to-version comparison.

NEVER:
  X returns raw chunk text to context
  X called by the LLM
  X sits in per-check runtime path
  X returns large payloads to the model
```

**Note on the vector store:** the chunked PDF text and embeddings you originally built (design_chunks, code_chunks) are barely used in this design. The engine reads values from extraction and properties from the Blue Book — it does not do vector search per check. The only survivor needing embeddings is `search_documents` for quick_answer. Most of the original Firestore vector setup becomes a small retrieval index for one feature, not the backbone.

## 5.2 Live Session State — Redis (or FastAPI process)

```
Redis SESSION[session_id] — live working state:
  document_index, section_properties,
  extracted_values, findings, formula_steps
  -> survives the session, NEVER enters context

Claude context holds ONLY:
  session_id + current findings summary
  -> ~300 tokens, flat, never grows
```

The old `WORKING_MEMORY` idea was correct in instinct, wrong in location. It does not live in the model's context and it is not a JS object tools pass around. It lives in Redis, keyed by session_id. Tools receive a session_id pointer, not the object.

## 5.3 Steel Blue Book Specifics

```
- web_fetch from steelforlifebluebook.co.uk
- do NOT store the full Blue Book (copyright)
- cache fetched properties in Firestore section_cache
- repeat access -> Firestore hit, no fetch
- citation always points to source URL: badge [SBB]
- section properties (A, Wpl, iz, Av, tf) come from the
  Blue Book, NEVER trusted from the design PDF
- these are AUTHORITATIVE values
```

---

# PART 6 — OUTPUT: THE OVERVIEW & PROSE STYLE

The overview is written by `write_overview` and is the most important prose in the product. Get the voice exactly right.

## 6.1 Overview Sentence Structure (in order, always)

```
S1  What was checked — document, element, codes. One sentence.
S2  How many checks ran — total + breakdown by status.
S3  The critical issue — what fails and why in plain terms.
    One or two sentences.
S4  What is correct, if anything. One sentence.
S5  Secondary issues — errors, missing, assumed — named
    briefly. One or two sentences.
S6-S7 Suggestions. SOFT tone. "it is suggested...". Two
    long comma-separated sentences.
S8  Closing: "Addressing these points together would put
    the design in a position to pass a full compliance
    review."
```

## 6.2 Prose Style Rules (ABSOLUTE)

```
- Full sentences, full words. No bullet points in the
  overview. No fragments.
- Small words over big words. "too weak" not
  "insufficient resistance".
- NO em dashes anywhere. They break reading flow.
- NO calculations mid-sentence. Numbers appear only as
  values (NEd = 6,896 kN), never as worked steps in prose.
- Numbers as digits (70%, 6,896 kN). Counts as words
  (three failures, two errors).
- Bold key items: document name, element name, code
  references, key values, key verdicts.
- Active voice. "The column exceeds the limit" not "the
  limit is exceeded by the column".
- The last two sentences are always SOFT and SUGGESTIVE.
  Never "must". Use "it is suggested", "could", "would
  be worth". This is the conclusion — professional and
  soft.
- Code references written in FULL: "Eurocode 3, Section
  6.3.1" — never "EC3 sec 6.3.1".
- Variable letters kept for ease of reading (NEd, Le, chi,
  lam_bar, Nb,Rd).
```

## 6.3 Overview Bold/Colour Treatment (from the reference render)

```
- In the overview, the status-count phrases inherit their
  status COLOUR as well as bold:
    "three failures"      -> red      (#A32D2D)
    "two errors"          -> amber    (#854F0B)
    "one missing check"   -> blue     (#185FA5)
    "one assumed value"   -> purple   (#534AB7)
    "one pass"            -> green    (#3B6D11)
  All other bolded items (document name, element name,
  code references, key values like NEd = 6,896 kN) use
  --text-primary at weight 500, NOT a colour.
```

## 6.4 The Finalised Overview (reference exemplar)

This is the exact **voice and structure** to reproduce. The specific numbers are
illustrative (see top-of-document note) — reproduce the sentence order and tone,
not these figures; the engine supplies the real values.

> This audit checked the base-level steel column in Building A (d3-solution.pdf) against Eurocode 3, Section 6.3.1 for buckling resistance and EN 1990, Section A1.3 for load combinations. Eight checks ran in total, returning three failures, two errors, one missing check, one assumed value, and one pass. The critical issue is the column section. The design axial load NEd is 6,896 kN, but the column can only resist 4,059 kN before it buckles, which means the section is carrying 70% more than the buckling limit allows. The load combination is correctly applied, so the problem is not how the loads were calculated but how the section was sized to resist them. Two errors also require attention before sign-off: the load combination applies the wrong partial factor to variable imposed loads, and an unexplained factor appears in the column area formula with no clause reference to justify it. One check required by Eurocode 3 is missing entirely, and one assumed value has not been verified against the actual section order. Before this design proceeds, it is suggested the column section size is revisited, as the current section sits well over the buckling limit and a larger section would increase both the squash load and the radius of gyration, reducing slenderness and raising the reduction factor simultaneously. It is also suggested the steel grade is confirmed against the actual section order, as the current assumption has not been verified against the flange thickness band, and if a lower grade applies, the yield strength drops and the section moves even further from passing the buckling limit. Addressing these points together would put the design in a position to pass a full compliance review.

## 6.5 The Three Verdict Phrasings (use per context)

```
1. AUDIT TABLE — verdict + evidence together
   "The column exceeds the buckling limit because
    NEd = 6,896 kN > Nb,Rd = 4,059 kN"

2. OVERVIEW — severity + ratio
   "The column exceeds the buckling limit by 70%
    (NEd / Nb,Rd = 1.70 > 1.0)"

3. RECOMMENDATION — fix target
   "The column sits 2,837 kN over the buckling limit
    (NEd = 6,896 kN, Nb,Rd = 4,059 kN)"
```

## 6.6 Recommended Actions Format

```
- 2 to 4 actions maximum
- Arrow bullet: ->
- First part BOLD — action verb + subject
- Then a dash, then specific values
- End with target clause or value

Finalised example (illustrative — see top-of-document note; reproduce the
arrow/bold/target shape, not the specific figures, which differ from 3.2):
->  Upsize column section — NEd = 6,896 kN exceeds
    Nb,Rd = 4,059 kN. Try UC 305 x 305 x 118 or larger.
->  Confirm steel grade against section order — if S275
    applies, fy drops from 355 to 265 N/mm2, reducing
    Npl,Rd by 1,175 kN.
->  Complete missing checks — shear against Vpl,Rd per
    Eurocode 3, Section 6.2.6 and deflection against
    L/360 per Section 7.2.1.
```

---

# PART 7 — OUTPUT: THE FINDINGS TABLE

## 7.1 Columns — Exactly Five

```
STATUS . CATEGORY . ISSUE . REFERENCE . ACTION

REMOVED: Party column, Clause column
(clause now written in full inside ISSUE and REFERENCE)

ROW ORDER (always): FAIL -> ERROR -> MISSING -> ASSUMED
                    -> WARNING -> PASS
```

## 7.2 Per-Column Style Rules

```
STATUS
  Coloured badge only. One of:
  FAIL / ERROR / MISSING / ASSUMED / WARNING / PASS

CATEGORY
  Heading (bold, 12px) + subheading (muted, 11px)
  Heading = what is being checked (noun phrase)
  Subheading = "Structural . ULS" / "Structural . SLS" /
               "Structural . material" / "Structural .
               resistance" / "Structural . classification"
  Example:
    Column buckling
    Structural . ULS

ISSUE
  Plain sentence stating the problem. Values in brackets
  (1.70 > 1.0). Two to three sentences max. No formulas
  in prose.
  ENDS with citation ref line:
    "Per Eurocode 3, Section 6.3.1 [1]"
  Can also add "Report [R]" when the issue is about an
  unreferenced value in the design document itself.

REFERENCE
  Italic quote from the source, SUMMARISED WITH ELLIPSES
  to show the full scope of the issue while staying
  concise (legal-clause style). Then the clause in full,
  then the pdf source line.
  Three parts, in order:
    "Nb,Rd = 0.878 x 4622.75 ... not greater than NEd -> FAIL"
    (Eurocode 3, Section 6.3.1). [1]
    > column_check_4.pdf . p.9-10 . Buckling Resistance

ACTION
  One short actionable sentence. Starts with a verb.
  Ends with the target clause or value.
  Example: "Upsize section. Try UC 305 x 305 x 118 or
  larger. Recheck chi and Nb,Rd."
```

## 7.3 The Ellipsis Reference Pattern (the model to follow)

The reference quote summarises a long passage while preserving its full scope, exactly like a legal clause citation:

```
GENERAL PATTERN (legal example for reference):
"Employer ... shall remain entitled to recover ... damages ...
 under common law ... and shall not be limited in any way
 whatsoever by the amount of liquidated damages ..."
 (Clause 16.3). [1]

OUR PATTERN:
"Nb,Rd = 0.878 x 4622.75 = 4059.17 kN ... not greater than
 NEd -> FAIL"
 (Eurocode 3, Section 6.3.1). [1]
 > column_check_4.pdf . p.9-10 . Buckling Resistance
```

## 7.4 The 10 Finalised Column Findings (reference target)

> *Illustrative reference rows (see top-of-document note): this shows the row
> format and the FAIL→ERROR→MISSING→ASSUMED→WARNING→PASS ordering. The ten-row
> count here intentionally differs from the eight cited in 6.4 — the engine
> produces the actual findings; do not transcribe these numbers as fact.*

```
FAIL     Column buckling      NEd = 6,896 kN > Nb,Rd = 4,059 kN (1.70 > 1.0)
FAIL     Load combinations    gQ = 1.35 applied, EN 1990 requires 1.50
FAIL     Column cross-section 1.05 factor, no clause reference
ERROR    Partial factor       gQ = 1.35 substituted for 1.50
ERROR    Unreferenced value   1.05 factor, no source/derivation
MISSING  Shear                VEd computed, never compared to Vpl,Rd
MISSING  Deflection           No SLS check for spans up to 10 m
ASSUMED  Steel grade          fy = 355 unverified vs thickness band
WARNING  Cross-section class  Class 1 asserted, no c/t ratio calculated
PASS     Load combination     gG = 1.35 correctly applied
```

---

# PART 8 — CITATIONS

## 8.1 Citation Rules

```
- Clause references written in FULL, no shorthand:
    "Eurocode 3, Section 6.3.1"  (NOT "EC3 sec 6.3.1")
- Citation badge is a CLICKABLE COLOURED badge linking
  to the clause
- Badge appears at END of ISSUE column:
    "Per Eurocode 3, Section 6.3.1 [1]"
- Badge appears in REFERENCE column after the quote:
    "(Eurocode 3, Section 6.3.1). [1]"
- PDF source lines kept as-is:
    "> column_check_4.pdf . p.9-10 . Buckling Resistance"
- The reference quote uses ellipses to show full scope
  while summarising
- FEATURE: citation clause can be called on ISOLATED
  questions — the quick_answer path may surface the same
  clickable clause badge when relevant
```

## 8.2 Badge Colour Map

```
[1]   blue    -> Eurocode 3
[2]   purple  -> EN 1990
[3]   green   -> EN 10025-2
[R]   amber   -> Report / design document
[SBB] orange  -> Steel Blue Book

Add new badge colours for new codes as needed
(e.g. EN 1993-1-8 for connections).
```

---

# PART 9 — THE HTML BOILERPLATE

This is the exact rendering contract. Every check reuses this structure. The placeholders map directly to data the engine or extract_element produces. Reproduce this styling precisely.

## 9.1 Light Theme Tokens (top of the style block)

```css
/* ── LIGHT THEME TOKENS (applies to all three views) ── */
:root {
  --surface-0:      #FAFAF8;   /* page background      */
  --surface-1:      #F4F3EF;   /* subtle card fill     */
  --surface-2:      #FFFFFF;   /* raised card / white  */
  --text-primary:   #1A1A18;   /* near-black body      */
  --text-secondary: #52514E;   /* muted body           */
  --text-muted:     #898781;   /* hints, axis labels   */
  --text-accent:    #185FA5;   /* links / pdf source   */
  --border:         rgba(26,26,24,0.10);   /* hairline */
  --border-strong:  rgba(26,26,24,0.18);
  --font-sans:      'Anthropic Sans', system-ui, sans-serif;
  --font-mono:      'Berkeley Mono', ui-monospace, monospace;
}
```

## 9.2 Full Boilerplate (styling + placeholders)

```html
<style>
  * { box-sizing: border-box; }
  .audit-wrap { width: 100%; font-family: var(--font-sans); color: var(--text-primary); }

  /* TITLE BLOCK */
  .section-label { font-size: 10px; font-weight: 500; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px; display: block; }
  .audit-title { font-size: 16px; font-weight: 500; color: var(--text-primary); margin: 0 0 4px 0; }
  .audit-sub { font-size: 12px; color: var(--text-muted); margin: 0 0 16px 0; }

  /* SUMMARY PILLS */
  .summary-pills { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
  .pill { display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px;
    border-radius: 20px; font-size: 11px; font-weight: 500; }
  .pill-fail    { background: #FCEBEB; color: #A32D2D; }
  .pill-error   { background: #FAEEDA; color: #854F0B; }
  .pill-missing { background: #E6F1FB; color: #185FA5; }
  .pill-assumed { background: #EEEDFE; color: #534AB7; }
  .pill-warning { background: #F1EFE8; color: #5F5E5A; }
  .pill-pass    { background: #EAF3DE; color: #3B6D11; }

  /* DIVIDER */
  .divider { border: none; border-top: 0.5px solid var(--border); margin: 20px 0; }

  /* OVERVIEW */
  .overview-body { font-size: 13px; line-height: 1.8; color: var(--text-primary); margin: 0 0 20px 0; }
  .overview-body strong { font-weight: 500; }

  /* RECOMMENDED ACTIONS */
  .actions-label { font-size: 10px; font-weight: 500; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--text-muted); margin: 0 0 10px 0; display: block; }
  .action-row { display: flex; gap: 10px; margin-bottom: 8px; font-size: 12px; line-height: 1.6; }
  .action-arrow { color: var(--text-muted); flex-shrink: 0; margin-top: 1px; }

  /* FINDINGS TABLE */
  .findings-wrap { width: 100%; overflow-x: auto; }
  .findings-header { display: flex; justify-content: space-between; align-items: baseline;
    padding: 0 0 10px 0; border-bottom: 1px solid var(--border-strong); }
  .findings-title { font-size: 10px; font-weight: 500; color: var(--text-muted);
    letter-spacing: 0.12em; text-transform: uppercase; }
  .findings-legend { font-size: 11px; color: var(--text-muted); }
  table { width: 100%; border-collapse: collapse; min-width: 860px; }
  thead th { text-align: left; padding: 10px 12px; font-size: 10px; font-weight: 500;
    color: var(--text-muted); letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap; }
  tbody tr { border-bottom: 0.5px solid var(--border); vertical-align: top; }
  tbody td { padding: 12px 12px; color: var(--text-primary); line-height: 1.6;
    font-size: 12px; font-family: var(--font-mono, monospace); }

  /* STATUS BADGES */
  .badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px;
    font-weight: 500; letter-spacing: 0.04em; white-space: nowrap; font-family: var(--font-sans); }
  .badge-fail    { background: #FCEBEB; color: #A32D2D; }
  .badge-error   { background: #FAEEDA; color: #854F0B; }
  .badge-missing { background: #E6F1FB; color: #185FA5; }
  .badge-assumed { background: #EEEDFE; color: #534AB7; }
  .badge-warning { background: #F1EFE8; color: #5F5E5A; }
  .badge-pass    { background: #EAF3DE; color: #3B6D11; }

  /* CATEGORY CELL */
  .category-label { font-family: var(--font-sans); font-size: 12px; font-weight: 500;
    color: var(--text-primary); display: block; margin-bottom: 2px; }
  .category-sub { font-family: var(--font-sans); font-size: 11px; color: var(--text-muted); }

  /* ISSUE CELL */
  .cite-ref { font-family: var(--font-sans); font-size: 11px; color: var(--text-muted);
    margin-top: 5px; display: block; }
  .cite-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px;
    font-weight: 600; cursor: pointer; text-decoration: none; margin-left: 2px; font-family: var(--font-sans); }
  .cite-ec3     { background: #E6F1FB; color: #185FA5; }
  .cite-en1990  { background: #EEEDFE; color: #534AB7; }
  .cite-en10025 { background: #EAF3DE; color: #3B6D11; }
  .cite-report  { background: #FAEEDA; color: #854F0B; }
  .cite-sbb     { background: #FAEEDA; color: #854F0B; }

  /* REFERENCE CELL */
  .ref-block  { font-style: italic; color: var(--text-secondary); font-size: 11px; line-height: 1.7; }
  .ref-clause { font-style: normal; color: var(--text-primary); font-size: 11px; margin-top: 4px; display: block; }
  .ref-source { color: #185FA5; font-size: 11px; display: block; margin-top: 3px; font-style: normal; }
</style>

<div class="audit-wrap">

  <!-- TITLE BLOCK -->
  <span class="section-label">Compliance Audit</span>
  <p class="audit-title">Check N — [Element Type] [Check Name]</p>
  <p class="audit-sub">[document.pdf] . [Project / Building] . [Element description]</p>

  <!-- SUMMARY PILLS: one per status that has >=1 row, count first -->
  <div class="summary-pills">
    <span class="pill pill-fail">N Fail</span>
    <span class="pill pill-error">N Error</span>
    <span class="pill pill-missing">N Missing</span>
    <span class="pill pill-assumed">N Assumed</span>
    <span class="pill pill-warning">N Warning</span>
    <span class="pill pill-pass">N Pass</span>
  </div>

  <hr class="divider">

  <!-- OVERVIEW: see Part 6 for the 8-sentence structure and voice -->
  <span class="section-label">Overview</span>
  <p class="overview-body">
    This audit checked the [element description] in <strong>[Project] ([document.pdf])</strong>
    against <strong>[Code, Section X.X.X]</strong> for [check type] ... [full paragraph,
    ending with the soft two-sentence suggestion and the closing line].
  </p>

  <hr class="divider">

  <!-- RECOMMENDED ACTIONS: 2-4, verb-first bold subject -->
  <span class="actions-label">Recommended Actions</span>
  <div class="action-row">
    <span class="action-arrow">-></span>
    <span><strong>[Action verb + subject]</strong> — [specific values]. [fix with target].</span>
  </div>

  <hr class="divider">

  <!-- FINDINGS TABLE -->
  <div class="findings-wrap">
    <div class="findings-header">
      <span class="findings-title">Findings — N</span>
      <span class="findings-legend">FAIL -> ERROR -> MISSING -> ASSUMED -> WARNING -> PASS</span>
    </div>
    <table>
      <thead>
        <tr>
          <th style="width:90px">Status</th>
          <th style="width:155px">Category</th>
          <th style="width:265px">Issue</th>
          <th style="width:240px">Reference</th>
          <th style="width:200px">Action</th>
        </tr>
      </thead>
      <tbody>
        <!-- ROW TEMPLATES BELOW, one per status -->
      </tbody>
    </table>
  </div>
</div>
```

## 9.3 Row Templates (one per status — the exact structure)

```html
<!-- FAIL ROW -->
<tr>
  <td><span class="badge badge-fail">FAIL</span></td>
  <td>
    <span class="category-label">[Check name — noun phrase]</span>
    <span class="category-sub">Structural . ULS</span>
  </td>
  <td>
    [Short sentence stating the failure. Include key values.
     e.g. "Exceeds bending limit because MEd = X kNm > Mc,Rd = Y kNm (ratio > 1.0)"]
    <span class="cite-ref">Per [Eurocode N, Section X.X.X]
      <a class="cite-badge cite-ec3" href="#" title="[Eurocode N, Section X.X.X — Description]">[1]</a></span>
  </td>
  <td>
    <span class="ref-block">"[Direct quote from document, summarised with ellipses ... to show full scope]"</span>
    <span class="ref-clause">([Eurocode N, Section X.X.X]).
      <a class="cite-badge cite-ec3" href="#" title="[Eurocode N, Section X.X.X]">[1]</a></span>
    <span class="ref-source">> [document.pdf . p.N . Section Name]</span>
  </td>
  <td>[Short verb-first action. e.g. "Upsize section. Try X or larger. Recheck Y."]</td>
</tr>

<!-- ERROR ROW -->
<tr>
  <td><span class="badge badge-error">ERROR</span></td>
  <td>
    <span class="category-label">[Error type — noun phrase]</span>
    <span class="category-sub">Structural . resistance</span>
  </td>
  <td>
    [Short sentence: what was done wrong and what should have been done.]
    <span class="cite-ref">Per [Eurocode N, Section X.X.X]
      <a class="cite-badge cite-ec3" href="#" title="...">[1]</a></span>
  </td>
  <td>
    <span class="ref-block">"[Quote from document showing the error ...]"</span>
    <span class="ref-clause">([Eurocode N, Section X.X.X]).
      <a class="cite-badge cite-ec3" href="#" title="...">[1]</a></span>
    <span class="ref-source">> [document.pdf . p.N . Section Name]</span>
  </td>
  <td>[Short action. e.g. "Correct X to Y. Rerun all downstream checks."]</td>
</tr>

<!-- MISSING ROW -->
<tr>
  <td><span class="badge badge-missing">MISSING</span></td>
  <td>
    <span class="category-label">[Check name that is absent]</span>
    <span class="category-sub">Structural . ULS</span>
  </td>
  <td>
    [Short sentence: what was computed or not, and what comparison is absent.
     e.g. "VEd computed but never compared to Vpl,Rd. Check entirely absent."]
    <span class="cite-ref">Per [Eurocode N, Section X.X.X]
      <a class="cite-badge cite-ec3" href="#" title="...">[1]</a></span>
  </td>
  <td>
    <span class="ref-block">"[Quote showing partial work or absence ... no comparison present]"</span>
    <span class="ref-clause">([Eurocode N, Section X.X.X]).
      <a class="cite-badge cite-ec3" href="#" title="...">[1]</a></span>
    <span class="ref-source">> [document.pdf . p.N . Section Name]</span>
  </td>
  <td>[Short: what to calculate and what limit to verify against.]</td>
</tr>

<!-- ASSUMED ROW -->
<tr>
  <td><span class="badge badge-assumed">ASSUMED</span></td>
  <td>
    <span class="category-label">[What was assumed — noun phrase]</span>
    <span class="category-sub">Structural . material</span>
  </td>
  <td>
    [Short sentence: what was assumed without verification and what it depends on.
     e.g. "fy taken as X N/mm2 without confirming thickness band. Result changes if lower grade applies."]
    <span class="cite-ref">Per [Code]
      <a class="cite-badge cite-en10025" href="#" title="...">[3]</a> . Report
      <a class="cite-badge cite-report" href="#" title="[document.pdf . p.N]">[R]</a></span>
  </td>
  <td>
    <span class="ref-block">"[Quote showing the assumed value stated without derivation ...]"</span>
    <span class="ref-clause">([Code reference]).
      <a class="cite-badge cite-en10025" href="#" title="...">[3]</a></span>
    <span class="ref-source">> [document.pdf . p.N . Section Name]</span>
  </td>
  <td>[Short: confirm X against Y. State consequence if assumption is wrong.]</td>
</tr>

<!-- WARNING ROW -->
<tr>
  <td><span class="badge badge-warning">WARNING</span></td>
  <td>
    <span class="category-label">[Qualitative check — noun phrase]</span>
    <span class="category-sub">Structural . classification</span>
  </td>
  <td>
    [Short sentence: what was asserted without a quantitative check.
     Always end with: "Engineer judgement required."]
    <span class="cite-ref">Per [Eurocode N, Section X.X.X]
      <a class="cite-badge cite-ec3" href="#" title="...">[1]</a></span>
  </td>
  <td>
    <span class="ref-block">"[Quote showing assertion without calculation ...]"</span>
    <span class="ref-clause">([Eurocode N, Section X.X.X]).
      <a class="cite-badge cite-ec3" href="#" title="...">[1]</a></span>
    <span class="ref-source">> [document.pdf . p.N . Section Name]</span>
  </td>
  <td>[Short: calculate X. Verify against Table Y or limit Z.]</td>
</tr>

<!-- PASS ROW -->
<tr>
  <td><span class="badge badge-pass">PASS</span></td>
  <td>
    <span class="category-label">[Check name — noun phrase]</span>
    <span class="category-sub">Structural . ULS</span>
  </td>
  <td>
    [Short sentence: what passed and what value was used correctly.]
    <span class="cite-ref">Per [Eurocode N, Section X.X.X]
      <a class="cite-badge cite-en1990" href="#" title="...">[2]</a></span>
  </td>
  <td>
    <span class="ref-block">"[Quote confirming the correct value or approach ...]"</span>
    <span class="ref-clause">([Eurocode N, Section X.X.X]).
      <a class="cite-badge cite-en1990" href="#" title="...">[2]</a></span>
    <span class="ref-source">> [document.pdf . p.N . Section Name]</span>
  </td>
  <td>None — compliant.</td>
</tr>
```

## 9.4 Placeholder -> Data Source Map

```
PLACEHOLDER               SOURCE
──────────────────────────────────────────────────────
[Element Type]            -> element classifier / index
[document.pdf]            -> file upload input
[Code, Section X.X.X]     -> check registry (clause field)
[N failures / N errors]   -> count of rows per status
[Direct quote ...]        -> extract_element (source quote)
[p.N . Section Name]      -> document index / chunk metadata
[key values]              -> classify() output + formula result
[Action sentence]         -> generated per check registry
[chi, lam_bar, Nb,Rd steps] -> formula function "steps" array
```

---

# PART 10 — TWO RESPONSE MODES

```
"check the column"          -> compliance_audit skill
                              full output: title, pills, overview,
                              actions, findings table, calc summary

"what is a better section"  -> quick_answer skill
                              flowing prose WITH quantities,
                              suggestion-oriented, no table,
                              inline citation if relevant

The prompt controls SCOPE. Same table structure, different rows:
  vague prompt      -> broad sweep -> many rows
  specific prompt   -> targeted    -> few rows
  element named     -> scoped to that element
  clause named      -> scoped to that clause
  status named      -> filtered by that status

Quick-action buttons (Check EC1, Check EC3, Summarise Risks)
are pre-written prompts mapping to specific scopes — same
tools, different instruction.
```

---

# PART 11 — FRONTEND FEATURES

```
VISUAL THEME — LIGHT
- Light theme across ALL three views (file list, PDF
  viewer, compliance chat sidebar). Consistent, not
  per-panel.
- Surfaces: near-white page background, white cards,
  hairline borders (0.5px, low-contrast grey).
- Monospace font for the audit output (findings, code
  refs, values). Sans-serif for chrome/labels.
- Status colours stay EXACTLY as finalised (the badge
  and pill palette) — they read cleanly on light and
  are the one place colour carries meaning.

DRAGGABLE PANEL BORDERS  <- critical for readability
- The vertical dividers between the three panels
  (file list <-> PDF viewer <-> chat sidebar) are
  draggable splitters.
- Dragging a border expands one panel and compresses
  its neighbour, so the engineer can widen the chat
  sidebar to read the full audit output (findings table,
  overview) without horizontal scroll, then widen the
  PDF back when reviewing the source.
- In the real app the right-view output is COMPRESSED
  (narrow column). The full-width rendering is only the
  expanded state. The output must render correctly at
  BOTH widths:
    narrow  -> findings table scrolls horizontally within
               its panel; overview wraps; nothing overflows
    wide    -> full table visible, as per the reference

IMPLEMENTATION NOTES
- Splitters: a draggable resize handle between flex
  panels (e.g. react-resizable-panels, or a simple
  mouse-drag handler updating panel flex-basis).
- Persist panel widths in memory only (NO localStorage /
  sessionStorage — they fail in the artifact sandbox).
- Findings table: table-layout with explicit column
  widths + a horizontal-scroll wrapper, so it never
  breaks columns regardless of panel width. Cell content
  must never fall below its column boundary at any width.
- Progressive rendering: findings rows stream in as each
  check completes.
- Real-time editing: edits apply on command while viewing
  the file (eventual product direction).

CRITICAL BROWSER RESTRICTION
- NO localStorage / sessionStorage in any rendered
  artifact. Use in-memory state only.
```

---

# PART 12 — THE FULL WORKFLOW (upload -> rendered output)

```
STAGE 0 — UPLOAD (deterministic, 0 AI, one time)
────────────────────────────────────────────────
1 parse PDF (PyMuPDF) -> document_index
   { elements, page ranges, section designations,
     codes referenced }
2 regex-match every section designation
   -> for each: check Firestore section_cache
       HIT  -> use cached properties
       MISS -> web_fetch Steel Blue Book -> cache it
3 store in Redis SESSION + Firestore document_index
4 notify: "Ready. N elements indexed:
           column (UC 254x254x132), beam (UB 610x178x100)."
   NO AI HAS RUN YET.

STAGE 1 — QUERY "check the column"
────────────────────────────────────────────────
route intent (keyword/cheap):
  "check the X"        -> compliance_audit path
  "what does X say"    -> quick_answer path

STAGE 2 — IDENTIFY (deterministic)
────────────────────────────────────────────────
match "column" against document_index.elements
  -> element_type = column, designation, pages
  (AI classify ONLY for genuinely ambiguous cases)

STAGE 3 — CACHE CHECK (deterministic, Firestore)
────────────────────────────────────────────────
for each check: key = hash(check_id + its inputs)
  ALL HIT  -> skip to Stage 6 render (< 1 s)
  ANY MISS -> proceed, only for missed checks

STAGE 4 — EXTRACT (1 AI call)
────────────────────────────────────────────────
[AI] extract_element
  -> strict JSON of all values for this element
  -> not_found list drives MISSING
  -> write to Redis SESSION

STAGE 5 — ENGINE (0 AI, tested Python, < 100ms)
────────────────────────────────────────────────
run_audit(element, values, section_props):
  registry lookup (dict) -> for each check:
    MISSING if input absent
    WARNING if qualitative clause
    else FORMULAS[id](inputs) -> classify() -> status
  national_annex lookup
  cross_reference -> CONFLICT detection
  -> write formula_cache, findings to SESSION

STAGE 6 — OVERVIEW (1 AI call, language only)
────────────────────────────────────────────────
[AI] write_overview
  -> overview paragraph + recommended actions
  -> CANNOT alter any verdict

STAGE 7 — ASSEMBLE + RENDER (deterministic)
────────────────────────────────────────────────
backend assembles structured JSON:
  { title_block, summary_pills, overview,
    recommended_actions, findings, calculation_summary }
compliance_audit skill governs FORMAT
calculation_summary skill governs calc blocks
-> write to Firestore audits/{firm}/{project}
-> return JSON to Next.js
-> frontend renders (progressive: rows stream in)

QUERY "what does clause 6.3.1 say"
────────────────────────────────────────────────
[AI] search_documents -> quick_answer skill formats reply
     with clickable clause citation

TOTAL: 2 AI calls per audit. Everything else is tested
Python or deterministic backend orchestration.
```

---

# PART 13 — FORMULA BUILD STRATEGY (tiers + how to build with Claude Code)

## 13.1 Tiers

```
TIER 1 — ships the product + YC demo (~80% of real checks)
  bending, shear, compression, flexural buckling, LTB,
  deflection SLS, load combination
  -> 7 formulas. Audits a beam and a column end to end.

TIER 2 — credible for real use
  combined bending + axial, cross-section classification,
  bolt shear + bearing, weld capacity

TIER 3 — completeness
  second order, fire, fatigue, plate buckling,
  block tearing, full National Annex coverage

Ship Tier 1. Seven TESTED formulas beat forty untested ones.
```

## 13.2 Building Formulas With Claude Code — The Rules

```
NEVER ask Claude Code to "write the buckling formula."
It will produce plausible-but-wrong code from memory.
Instead: give it the primary source + the known answer,
and make it write code that reproduces the answer.
The test is the specification, not the prose.

PER FORMULA:
1. YOU transcribe the lookup tables from the printed
   standard into tables/*.py. Claude must NEVER recall
   coefficients — a misremembered alpha of 0.34 vs 0.49
   gives a wrong-but-plausible number.
2. YOU supply TWO independent known answers (coursework,
   Blue Book published resistances, textbook examples).
3. Test-first prompt: "Write the test with this known
   answer FIRST, then the function to pass it. Use these
   exact table values: [...]. Show every intermediate
   step. Do not use any table value I haven't given you —
   if you need one, stop and ask."
4. Claude annotates each step with its clause so you can
   verify line-by-line against printed EC3.
5. Both tests must pass. One pass = luck; two independent
   answers = generalises.
6. YOU verify the annotated steps against the source.
7. Commit. CI now guards it forever.

~30-45 min per formula with verification.
Tier 1 (7 formulas) ~ one focused day.

FILES:
- /reference (gitignored): Eurocode PDF, worked examples,
  coursework, Blue Book extracts — Claude READS these
- formulas/, tables/, tests/ — Claude WRITES (you verify),
  YOU transcribe tables
- Eurocode PDF gitignored (copyright). Transcribed numbers
  in tables/ are fine (facts aren't copyrightable).

THE ONE RULE:
Claude Code writes the CODE. YOU own the CORRECTNESS.
The test (your known answer) is the contract. The tables
(your transcription) are ground truth. Claude fills the
logic between them and shows its working. Never let Claude
be the authority on what the Eurocode says — let it be the
authority on turning your verified inputs into passing
tested code.
```

## 13.3 Where To Start

```
formula #1: flexural_buckling
You already have the hand-worked answer from Check 8:
  NEd=6896.25, A=168.1, iz=6.69, Le=3.22, fy=275,
  UC minor -> chi=0.878, Nb,Rd=4059 kN

1. Write formulas/flexural_buckling.py (see 4.2)
2. Write tables/buckling_curves.py, tables/imperfection.py
3. Write tests/test_flexural_buckling.py asserting
   chi=0.878 and Nb,Rd=4059.2
4. Run the test. Watch it pass.
5. Add "flexural_buckling" to CHECK_REGISTRY under "column"

That's formula one of seven. Repeat six times -> demoable
product with a validated engine and honest coverage.
```

---

# PART 14 — OPEN ITEMS TO RESOLVE DURING THE REFACTOR

```
1. PROFILE FIRST. Instrument every tool with timing before
   optimising. The 9-minute runtime was assumed to be
   context bloat but is almost certainly nested LLM calls
   inside the old value_extractor and result_comparator.
   Confirm the real bottleneck with numbers before
   refactoring around a guess.

2. BUILD THE FORMULA TEST SUITE FIRST. It is the liability
   firewall. No formula goes live until it reproduces a
   hand-worked answer to 3 sig figs, gated in CI.

3. STATE LOCATION. Confirm Redis vs FastAPI process memory
   for session state. Redis if you want it to survive
   restarts (recommended). Tools get a session_id pointer,
   never the state object. This is a correctness fix.

4. WIRE CONFLICT DETECTION. It is designed but not
   connected. The known case: S275 in the calc PDF (fy=275)
   vs S355 in the design report (fy=355). cross_reference()
   must read both element sections and flag CONFLICT.

5. ERROR HANDLING EVERYWHERE. Every tool failure maps to a
   status (MISSING / ASSUMED), never a crash. Define the
   failure mode for: value not found, Blue Book fetch
   timeout, null formula input, invalid extraction JSON.

6. element_classifier CONFIDENCE THRESHOLD. Define behaviour
   below a threshold (e.g. 0.6): ask the user vs default vs
   skip. The confidence score must be consumed, not
   decorative.

7. CACHE KEY GRANULARITY. formula_cache is keyed per check
   on its specific inputs, NOT whole-document hash. Verify
   this is implemented so editing one value invalidates
   only dependent checks.

8. section_property_lookup REDUNDANCY. If prefetch loads all
   properties on upload, there is no separate mid-audit
   property tool. Confirm properties are fetched once on
   upload and read from session state thereafter.
```

---

# PART 15 — WHAT IS GENUINELY GOOD (keep, do not touch)

```
- The summary-not-raw-text principle (return structured
  summaries to context, never raw chunk text). This is the
  single most valuable idea — it solves the TPM problem.
- The check registry enforcing MISSING via a deterministic
  loop over the complete required set.
- Splitting formula verification into extract / run /
  compare (now: extract_element AI, formulas Python,
  classify Python).
- The status taxonomy (FAIL / ERROR / MISSING / ASSUMED /
  WARNING / PASS + CONFLICT) — better than most commercial
  tools.
- The caching instinct (fix the keying to per-check).
- The output format, citation system, and boilerplate —
  finalised and correct. Reproduce exactly.
- The overview voice — soft, professional, full-sentence,
  no em dashes, suggestions last. Finalised exemplar in 6.4.
- The light theme + draggable panel borders.
```

---

# SUMMARY — THE ONE-PARAGRAPH BRIEF

COMPLY is a tested deterministic Eurocode-checking engine wrapped in a thin AI membrane. Three MCP tools (`extract_element` reads a PDF element into strict JSON, `write_overview` narrates finished findings, `search_documents` retrieves clause prose for Q&A) and three skills (`compliance_audit`, `quick_answer`, `calculation_summary`) — all skills are format contracts, never orchestrators. Everything engineering — 40+ formulas as pure functions split from transcribed lookup tables, the check registry as a dict, `classify()` for status, cross-reference for CONFLICT, caching, and session state — is deterministic Python in the backend, unit-tested against hand-worked answers and gated in CI. Firestore lives only at the edges (section-property cache, per-check formula cache, document index, clause-prose vector store for Q&A, and audit history), never in the hot path and never called by the LLM; live session state is in Redis keyed by session_id, so context stays flat at ~300 tokens. The workflow is: parse and cache on upload (0 AI) -> one extraction call -> deterministic engine -> one overview call -> assemble and render, for 2 AI calls per audit and ~10-15s first-run, ~1-2s cached. The output is the finalised format — a light-themed UI with draggable panel borders, a title block, coloured status pills, a full-sentence overview with soft suggestions and status-coloured count phrases, 2-4 recommended actions, a five-column findings table (status/category/issue/reference/action) with ellipsis-summarised reference quotes, full-text clause names, clickable coloured citation badges, and per-check collapsible calculation summaries; the output renders correctly at both narrow (real, compressed) and wide (expanded) panel widths. Build Tier 1's seven formulas first, each validated against your coursework, with Claude Code writing test-first code from tables you transcribe and answers you supply — Claude owns the typing, you own the correctness.