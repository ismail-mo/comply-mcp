import Anthropic from "@anthropic-ai/sdk";
import { embedQuery, vectorSearch } from "../lib/firebase.js";

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export const extract_design_values = {
  name: "extract_design_values",
  description: `Extract structured numeric design claims from the design report.
    Returns a list of {parameter, value, unit, page, source_quote, element_type, element_id, derived, formula, raw_inputs}.
    Stated results are passed through directly; M_Ed, V_Ed and deflection are also derived from raw inputs where available.
    Optionally filter by element_type (beam, column, slab, connection, foundation) or parameter.`,
  inputSchema: {
    type: "object",
    properties: {
      element_type: {
        type: "string",
        description: "Optional: beam, column, slab, connection, foundation",
      },
      parameter: {
        type: "string",
        description: "Optional: e.g. 'bending moment', 'axial load', 'minimum slope'",
      },
    },
  },

  handler: async ({ element_type, parameter } = {}) => {
    let query = `${element_type || ""} ${parameter || ""} design value calculation span load section`.trim();
    if (!query) query = "design values calculations sizing span load";

    const queryEmbed = await embedQuery(query);
    const chunks = await vectorSearch("design_chunks", queryEmbed, 10);

    const chunkText = chunks
      .map((c, i) => `--- chunk ${i} (p.${c.page ?? "?"}) ---\n${c.text}`)
      .join("\n\n");

    // ── Stage 1: Extract all raw structural inputs ────────────────────────
    const stageOnePrompt = `You are a structural engineer reading a design report.
From the chunks below, extract every piece of structural data you can find.

Return a JSON object with this schema:
{
  "elements": [
    {
      "element_id":    "<name or description, e.g. 'internal primary beam'>",
      "element_type":  "<beam|column|slab|connection|foundation>",
      "page":          <page number or null>,
      "raw_inputs": {
        "span_m":        <number or null>,
        "load_uls_kNm":  <ULS uniformly distributed load in kN/m, or null>,
        "load_sls_kNm":  <SLS/quasi-permanent UDL in kN/m, or null>,
        "load_point_kN": <point load in kN, or null>,
        "section":       "<section designation e.g. '610x229x101 UB', or null>",
        "steel_grade":   "<e.g. 'S355', or null>",
        "f_y_Nmm2":      <yield strength in N/mm², or null>,
        "W_pl_y_cm3":    <plastic section modulus in cm³, or null>,
        "A_v_mm2":       <shear area in mm², or null>,
        "I_y_cm4":       <second moment of area in cm⁴, or null>
      },
      "stated_results": [
        {
          "parameter":    "<e.g. 'bending moment', 'shear force', 'deflection'>",
          "value":        <number>,
          "unit":         "<SI unit>",
          "source_quote": "<exact phrase from report, max 12 words>"
        }
      ]
    }
  ]
}

Rules:
- Extract every element you can find (beams, columns, slabs, connections).
- raw_inputs: only put values EXPLICITLY stated in the text; null means not found.
- stated_results: results that are explicitly given in the report as a calculated answer.
- If the same element appears in multiple chunks, merge into one entry.
- Return [] for elements if none found.

CHUNKS:
${chunkText}

Return ONLY the JSON object. No prose.`;

    const stageOneResponse = await anthropic.messages.create({
      model: "claude-opus-4-7",
      max_tokens: 3000,
      system: "You extract structured JSON from engineering documents. Return only valid JSON.",
      messages: [{ role: "user", content: stageOnePrompt }],
    });

    let extracted = { elements: [] };
    try {
      const raw = stageOneResponse.content[0].text.trim();
      const match = raw.match(/\{[\s\S]*\}/);
      extracted = JSON.parse(match ? match[0] : raw);
    } catch {
      extracted = { elements: [] };
    }

    // ── Stage 2: Calculate design actions from raw inputs ─────────────────
    const E_steel = 210000; // N/mm²

    const claims = [];

    for (const el of extracted.elements ?? []) {
      const base = {
        element_id:   el.element_id,
        element_type: el.element_type,
        page:         el.page,
      };
      const inp = el.raw_inputs ?? {};

      // Carry forward any explicitly stated results first
      for (const r of el.stated_results ?? []) {
        claims.push({
          ...base,
          parameter:    r.parameter,
          value:        r.value,
          unit:         r.unit,
          source_quote: r.source_quote,
          derived:      false,
          raw_inputs:   inp,
        });
      }

      const L  = inp.span_m;
      const w  = inp.load_uls_kNm;
      const ws = inp.load_sls_kNm;

      // Bending moment M_Ed = wL²/8 (ULS UDL, simply-supported)
      if (L && w && !el.stated_results?.some(r => r.parameter.toLowerCase().includes("bending"))) {
        const M_Ed = Math.round((w * L * L / 8) * 10) / 10;
        claims.push({
          ...base,
          parameter:    "bending moment",
          value:        M_Ed,
          unit:         "kNm",
          source_quote: `span ${L}m, ULS UDL ${w} kN/m`,
          derived:      true,
          formula:      "M_Ed = wL²/8",
          raw_inputs:   inp,
        });
      }

      // Shear force V_Ed = wL/2 (ULS UDL, simply-supported)
      if (L && w && !el.stated_results?.some(r => r.parameter.toLowerCase().includes("shear"))) {
        const V_Ed = Math.round((w * L / 2) * 10) / 10;
        claims.push({
          ...base,
          parameter:    "shear force",
          value:        V_Ed,
          unit:         "kN",
          source_quote: `span ${L}m, ULS UDL ${w} kN/m`,
          derived:      true,
          formula:      "V_Ed = wL/2",
          raw_inputs:   inp,
        });
      }

      // Deflection δ = 5wL⁴/(384EI) (SLS UDL, simply-supported)
      const I_mm4 = inp.I_y_cm4 ? inp.I_y_cm4 * 1e4 : null; // cm⁴ → mm⁴
      if (L && ws && I_mm4 && !el.stated_results?.some(r => r.parameter.toLowerCase().includes("deflect"))) {
        const L_mm  = L * 1000;
        const w_Nmm = ws; // kN/m = N/mm (×1000 N/kN ÷ 1000 mm/m, net factor = 1)
        const delta = Math.round((5 * w_Nmm * Math.pow(L_mm, 4)) / (384 * E_steel * I_mm4) * 10) / 10;
        claims.push({
          ...base,
          parameter:    "deflection",
          value:        delta,
          unit:         "mm",
          source_quote: `span ${L}m, SLS UDL ${ws} kN/m`,
          derived:      true,
          formula:      "δ = 5wL⁴/(384EI)",
          raw_inputs:   inp,
        });
      }
    }

    const filtered = claims
      .filter((c) => !element_type || c.element_type?.toLowerCase() === element_type.toLowerCase())
      .filter((c) => !parameter   || c.parameter?.toLowerCase().includes(parameter.toLowerCase()));

    return { claims: filtered, total: filtered.length };
  },
};
