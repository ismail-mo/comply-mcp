# Kickoff — COMPLY refactor (for Fable 5)

Read `prompts/prompt1.md` in full — it is the complete build spec (a deterministic
Eurocode compliance auditor with a thin AI membrane). Then skim `CLAUDE.md` and
`backend/mcp/server.py` for what already exists.

**Then: plan the phases yourself from the spec, and one-shot the whole build —
execute every phase in your plan end to end without stopping for sign-off.** Do
not pause between phases; only stop if you hit a genuine blocker or an ambiguity
that would make you guess a Eurocode value (then ask).

Follow the spec's governing philosophy exactly: deterministic Python does ALL
engineering (formulas, pass/fail, status); the AI only extracts values and writes
prose. Never let the model run a formula or decide a verdict. Keep the existing
token discipline (Part 15).

---

## Groundwork already done — use it, don't redo it

**Reference docs are in `reference/` (already gitignored — do not commit them).**
The spec's Part 4.1 filenames differ from what's actually there; use these:

| Spec expects | Actual file in `reference/` |
|---|---|
| eurocode3.pdf | `eur3.pdf` (verified BS EN 1993-1-1) |
| — EN 1990 | `en.1990.2002.pdf` |
| — Eurocode 1 | `eur1.pdf` |
| blue_book_extract.pdf | `sci-p363-steel-building-design-design-data-blue-book.pdf` (verified genuine SCI P363, 591 pp) |
| worked_examples.pdf | `sci-p364-worked-examples-open-sections.pdf` (verified SCI P364, EC3, step-by-step) |
| coursework/ | `des3 group project.pdf` (the design report under audit) |

Both SCI PDFs verified as EC3 (not BS 5950). `.gitignore` already excludes
`reference/`. Transcribe the section-property and coefficient numbers into
`tables/*.py` (facts, committed); never commit the PDFs.

## Known-answer oracle — already extracted, hardcode these into `tests/`

Two independent authoritative answers per formula (spec Part 13.2). γM0=γM1=1.0.

**`flexural_buckling` (Nb,Rd)** — TWO oracles:
- Coursework Check 8: UC 254×254×132, S275, NEd=6896.25 kN, A=168.1 cm², iz=6.69 cm,
  Le=3.22 m → λ̄=0.513, χ=0.878, Nb,Rd=4059.2 kN
- P364 Ex 9: UKC 356×368×129, S355, NEd=3500 kN, A=164 cm², iz=9.43 cm, Lcr=6000 mm,
  curve c (α=0.49) → λ̄z=0.82, χ=0.65, Nb,Rd=3678 kN (Blue Book 3670)

**`compression` (Nc,Rd)** — P364 Ex 9: A=164 cm², fy=345 → Nc,Rd=5658 kN (Blue Book 5660)

**`bending` (Mc,Rd)** — P364 Ex 2: Wpl,y=2360 cm³, fy=275 → Mc,Rd=649.0 kNm

**`shear` (Vpl,Rd)** — P364 Ex 2: Av=5723.6 mm² (A=117 cm², b=209.3, tf=15.6, tw=10.1,
r=12.7, hw=501.9, fy=275) → Vpl,Rd=909 kN

**`deflection` (SLS)** — P364 Ex 2: variable-only q=30 kN/m, Q=50 kN, L=6500 mm,
E=210000, Iy=55200 cm⁴ → w=8.5 mm, wlim=L/360=18.1 mm

**`load_combo`** — P364 Ex 2 (EN 1990 Eq 6.10b, γG=1.35, γQ=1.50, ξ=0.925): g=15 kN/m,
G=40 kN, q=30 kN/m, Q=50 kN → F1,d=63.7 kN/m, F2,d=125.0 kN; MEd=539.5 kNm, VEd=269.5 kN

**`ltb` (Mb,Rd)** — NOT yet extracted. Pull it yourself from `reference/…p364…pdf`
**Example 3** (Unrestrained beam with end moments, ~p29–38) before writing that test.

Section properties captured for `tables/section_properties.py`:
- 533×210×92 UKB (S275): A=117 cm², Wpl,y=2360 cm³, Iy=55200 cm⁴, tf=15.6, tw=10.1, r=12.7
- 356×368×129 UKC (S355): A=164 cm², iy=15.6 cm, iz=9.43 cm, tf=17.5, tw=10.4, r=15.2
- 254×254×132 UKC: A=168.1 cm², iz=6.69 cm, Wpl,y=1870 cm³, tf=25.3, tw=15.3

---

## Test loop — run it, iterate to green

Work formula-by-formula, test-first:
1. Write `tests/test_<formula>.py` asserting the known answers above (both oracles
   where two exist), matched to the precision the source carries.
2. Write `formulas/<formula>.py` + any `tables/*.py` (transcribe coefficients from
   `reference/eur3.pdf` — never recall α, curves, or ε from memory).
3. **Run `pytest tests/test_<formula>.py -q`.** If red, fix ONLY the formula or the
   transcribed table — NEVER change a test's expected value or loosen a tolerance to
   force a pass. If a test looks wrong, stop and ask.
4. Loop until green, annotate each formula step with its EC3 clause, then next formula.

After all 7 Tier-1 formulas are green, build the engine (`run_audit`, `classify`,
`cross_reference`, registry) and snapshot a full Check-8 audit to
`tests/golden/check8.json`. Run the whole suite (`pytest -q`) after every change and
report the summary. Then proceed to the tools and frontend phases per your plan.

**Non-negotiables:** the AI never computes or decides a verdict; never invent a
Eurocode coefficient; never edit a test oracle to pass. Correctness is owned by the
transcribed sources, not by you.
