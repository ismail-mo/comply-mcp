import Anthropic from "@anthropic-ai/sdk";

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export const compare_value_to_clause = {
  name: "compare_value_to_clause",
  description: `Compares a single design value against a Eurocode clause and returns a structured
    pass/fail verdict with delta. Use this AFTER extract_design_values AND retrieve_code_clauses.`,
  inputSchema: {
    type: "object",
    properties: {
      design_claim: {
        type: "object",
        description:
          "From extract_design_values: {parameter, value, unit, page, source_quote, element_type, element_id}",
      },
      code_clause: {
        type: "object",
        description:
          "From retrieve_code_clauses: {clause_text, clause_number, code, page}",
      },
    },
    required: ["design_claim", "code_clause"],
  },

  handler: async ({ design_claim, code_clause }) => {
    // Serialise section properties so Claude can use them in capacity calculations
    const rawCtx = design_claim.raw_inputs
      ? JSON.stringify(design_claim.raw_inputs, null, 2)
      : "(no section properties available)";

    const derivedNote = design_claim.derived
      ? `Design value was calculated using formula: ${design_claim.formula ?? "standard formula"}`
      : "Design value was explicitly stated in the design report.";

    const verdictPrompt = `You are a structural engineer performing a Eurocode compliance check.

═══════════════════════════════════
DESIGN DEMAND
═══════════════════════════════════
  Parameter:   ${design_claim.parameter}
  Value:       ${design_claim.value ?? "NOT PROVIDED"} ${design_claim.unit ?? ""}
  Element:     ${design_claim.element_id || "unspecified"} (${design_claim.element_type || "unknown"})
  Source:      "${design_claim.source_quote}" (p.${design_claim.page ?? "?"})
  ${derivedNote}

Section / material properties from the design report (use these in resistance calculations):
${rawCtx}

═══════════════════════════════════
GOVERNING CODE CLAUSE
═══════════════════════════════════
  ${code_clause.clause_text}
  (Reference: ${code_clause.code ?? "Eurocode"}, clause ${code_clause.clause_number ?? "—"})

═══════════════════════════════════
YOUR TASK
═══════════════════════════════════
1. Identify the resistance formula in the clause (e.g. M_c,Rd = W_pl,y × f_y / γ_M0).
2. Substitute known values from the section properties above. Use standard Eurocode
   defaults for any missing partial factors (γ_M0 = 1.0, γ_M1 = 1.0).
3. Calculate the resistance (capacity) step by step.
4. Compare demand vs capacity and compute utilization = (demand / capacity) × 100.
5. Assign verdict: PASS if utilization ≤ 100%, FAIL if > 100%, REVIEW if calculation
   is not possible (qualitative clause, missing key data, unit mismatch).

Return ONLY this JSON (all fields required):
{
  "verdict":            "PASS" | "FAIL" | "REVIEW",
  "capacity_value":     <number or null>,
  "capacity_unit":      "<unit>",
  "capacity_formula":   "<formula used, e.g. 'M_c,Rd = W_pl,y × f_y / γ_M0'>",
  "utilization_pct":    <number 0-999 or null>,
  "margin":             <capacity_value minus demand_value, signed, or null>,
  "margin_unit":        "<same unit as capacity>",
  "calculation_steps":  ["<step 1 as string>", "<step 2>", ...],
  "comparison_op":      ">=" | "<=" | "==" | "n/a",
  "explanation":        "<one-sentence engineering verdict, max 30 words>"
}

Critical rules:
- If design value is null/missing, set verdict to REVIEW, all numbers to null.
- If a capacity formula is in the clause but section data is missing, still compute
  what you can and REVIEW the rest — never fabricate a value you cannot support.
- NEVER invent a clause threshold. If it isn't in the clause text, use REVIEW.`;

    const response = await anthropic.messages.create({
      model: "claude-opus-4-7",
      max_tokens: 1500,
      system: "You are a structural engineer performing Eurocode compliance checks. Return only valid JSON.",
      messages: [{ role: "user", content: verdictPrompt }],
    });

    let verdict = {
      verdict: "REVIEW",
      capacity_value: null,
      capacity_unit: "",
      capacity_formula: "Could not determine",
      utilization_pct: null,
      margin: null,
      margin_unit: "",
      calculation_steps: ["Comparison could not be completed — check inputs"],
      comparison_op: "n/a",
      explanation: "Could not parse comparison result",
    };
    try {
      const raw = response.content[0].text.trim();
      const match = raw.match(/\{[\s\S]*\}/);
      verdict = JSON.parse(match ? match[0] : raw);
    } catch {
      // keep default REVIEW
    }

    // Normalize verdict to exactly PASS / FAIL / REVIEW so report counting works
    const rawVerdict = String(verdict.verdict ?? "").toUpperCase();
    verdict.verdict = rawVerdict.startsWith("PASS")
      ? "PASS"
      : rawVerdict.startsWith("FAIL")
      ? "FAIL"
      : "REVIEW";

    return {
      design_claim,
      code_clause,
      ...verdict,
    };
  },
};
