import { writeFileSync, appendFileSync, existsSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const AUDITS_DIR = join(__dirname, "../../audits");

export const write_audit_report = {
  name: "write_audit_report",
  description: `Writes a structured compliance audit to a .txt file in /audits.
    Pass an array of comparison results from compare_value_to_clause.
    Returns the file path so the user can open it.`,
  inputSchema: {
    type: "object",
    properties: {
      findings: {
        type: "array",
        description:
          "Array of results from compare_value_to_clause: [{design_claim, code_clause, verdict, capacity_value, capacity_unit, capacity_formula, utilization_pct, margin, margin_unit, calculation_steps, comparison_op, explanation}]",
      },
      mode: {
        type: "string",
        description:
          "'full' creates a timestamped audit file; 'append' adds to single-checks.txt",
        default: "full",
      },
      project_name: {
        type: "string",
        description: "Project label used in the filename and header",
        default: "audit",
      },
    },
    required: ["findings"],
  },

  handler: async ({ findings, mode = "full", project_name = "audit" }) => {
    if (!existsSync(AUDITS_DIR)) mkdirSync(AUDITS_DIR, { recursive: true });

    const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const filename =
      mode === "append"
        ? "single-checks.txt"
        : `${project_name}-audit-${timestamp}.txt`;
    const filepath = join(AUDITS_DIR, filename);

    // ── Normalize verdict: tolerate "FAIL - CRITICAL", "PASS (CONDITIONAL)", etc. ─
    const normalizeVerdict = (v) => {
      const up = String(v ?? "").toUpperCase();
      if (up.startsWith("PASS"))   return "PASS";
      if (up.startsWith("FAIL"))   return "FAIL";
      return "REVIEW";
    };

    // ── Summary statistics ─────────────────────────────────────────────────
    const counts = { PASS: 0, FAIL: 0, REVIEW: 0 };
    for (const f of findings) counts[normalizeVerdict(f.verdict)]++;

    const complianceRate =
      findings.length > 0
        ? ((counts.PASS / findings.length) * 100).toFixed(1)
        : "0.0";

    const utilizations = findings
      .map((f) => f.utilization_pct)
      .filter((u) => typeof u === "number" && !isNaN(u));

    const maxUtil = utilizations.length
      ? Math.max(...utilizations).toFixed(1)
      : null;
    const avgUtil = utilizations.length
      ? (utilizations.reduce((s, u) => s + u, 0) / utilizations.length).toFixed(1)
      : null;
    const controllingFinding = maxUtil
      ? findings.find((f) => f.utilization_pct?.toFixed(1) === maxUtil)
      : null;

    // ── Group by element type ──────────────────────────────────────────────
    const grouped = {};
    for (const f of findings) {
      const key = f.design_claim?.element_type || "uncategorised";
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(f);
    }

    // ── Build report ───────────────────────────────────────────────────────
    let report = "";
    const W = 67; // line width
    const bar = "═".repeat(W);
    const dash = "─".repeat(W);

    report += `${bar}\n`;
    report += `   STRUCTURAL COMPLIANCE AUDIT\n`;
    report += `   Generated: ${new Date().toUTCString()}\n`;
    report += `   Project:   ${project_name}\n`;
    report += `${bar}\n\n`;

    // Summary block
    report += `SUMMARY\n`;
    report += `   Total checks:    ${findings.length}\n`;
    report += `   ✓ PASS:          ${counts.PASS}\n`;
    report += `   ✗ FAIL:          ${counts.FAIL}\n`;
    report += `   ⚠ REVIEW:        ${counts.REVIEW}\n`;
    report += `   Compliance rate: ${complianceRate}%  (${counts.PASS}/${findings.length} checks pass)\n`;
    if (maxUtil !== null) {
      report += `   Max utilization: ${maxUtil}%`;
      if (controllingFinding) {
        report += `  (${controllingFinding.design_claim?.parameter ?? "unknown"} — ${controllingFinding.design_claim?.element_id ?? controllingFinding.design_claim?.element_type ?? ""})`;
      }
      report += "\n";
    }
    if (avgUtil !== null) {
      report += `   Avg utilization: ${avgUtil}%\n`;
    }
    report += `\n${dash}\n\n`;

    // Per-element findings
    let checkIndex = 0;
    for (const [elementType, items] of Object.entries(grouped)) {
      report += `▸ ${elementType.toUpperCase()}\n\n`;

      for (const f of items) {
        checkIndex++;
        const v   = normalizeVerdict(f.verdict);
        const sym = v === "PASS" ? "✓" : v === "FAIL" ? "✗" : "⚠";
        const dc  = f.design_claim ?? {};
        const cc  = f.code_clause  ?? {};

        report += `  CHECK ${checkIndex}: ${(dc.parameter ?? "unknown").toUpperCase()}`;
        if (cc.clause_number && cc.clause_number !== "see source") {
          report += `  (${cc.clause_number})`;
        }
        report += "\n\n";

        report += `    Element:       ${dc.element_id || dc.element_type || "—"}\n`;

        // Design demand
        report += `    Design value:  `;
        if (dc.value !== null && dc.value !== undefined) {
          report += `${dc.value} ${dc.unit ?? ""}`;
          if (dc.derived && dc.formula) report += `  [calculated: ${dc.formula}]`;
          report += `\n`;
        } else {
          report += `NOT AVAILABLE\n`;
        }
        report += `    Source:        "${dc.source_quote ?? "—"}" (p.${dc.page ?? "?"})\n`;

        // Code requirement
        report += `    Code clause:   ${cc.code ?? "Eurocode"}, clause ${cc.clause_number ?? "—"}\n`;
        if (f.capacity_formula && f.capacity_formula !== "Could not determine") {
          report += `    Formula:       ${f.capacity_formula}\n`;
        }

        // Calculation steps (if present)
        if (Array.isArray(f.calculation_steps) && f.calculation_steps.length > 0) {
          report += `    Calculation:\n`;
          for (const step of f.calculation_steps) {
            report += `      → ${step}\n`;
          }
        }

        // Capacity and utilization
        if (f.capacity_value !== null && f.capacity_value !== undefined) {
          report += `    Capacity:      ${f.capacity_value} ${f.capacity_unit ?? ""}\n`;
        }
        if (f.utilization_pct !== null && f.utilization_pct !== undefined) {
          report += `    Utilization:   ${f.utilization_pct.toFixed(1)}%  `;
          report += f.utilization_pct <= 100
            ? `(${(100 - f.utilization_pct).toFixed(1)}% reserve)\n`
            : `(EXCEEDS capacity by ${(f.utilization_pct - 100).toFixed(1)}%)\n`;
        }
        if (f.margin !== null && f.margin !== undefined) {
          const sign = f.margin >= 0 ? "+" : "";
          report += `    Margin:        ${sign}${f.margin} ${f.margin_unit ?? ""}\n`;
        }

        // Verdict
        report += `\n    [${sym} ${v}]  ${f.explanation ?? ""}\n\n`;
      }
    }

    // Trailing summary of failures / reviews
    const failures = findings.filter((f) => normalizeVerdict(f.verdict) === "FAIL");
    const reviews  = findings.filter((f) => normalizeVerdict(f.verdict) === "REVIEW");
    if (failures.length || reviews.length) {
      report += `${dash}\n\n`;
      if (failures.length) {
        report += `ITEMS REQUIRING ACTION (${failures.length} FAIL)\n`;
        for (const f of failures) {
          report += `   ✗  ${f.design_claim?.parameter ?? "?"} — ${f.design_claim?.element_id ?? f.design_claim?.element_type ?? "?"}\n`;
          report += `      ${f.explanation ?? ""}\n`;
          if (f.utilization_pct !== null && f.utilization_pct !== undefined) {
            report += `      Utilization: ${f.utilization_pct.toFixed(1)}%\n`;
          }
          report += "\n";
        }
      }
      if (reviews.length) {
        report += `ITEMS FOR MANUAL REVIEW (${reviews.length} REVIEW)\n`;
        for (const f of reviews) {
          report += `   ⚠  ${f.design_claim?.parameter ?? "?"} — ${f.design_claim?.element_id ?? f.design_claim?.element_type ?? "?"}\n`;
          report += `      ${f.explanation ?? ""}\n\n`;
        }
      }
    }

    report += `${bar}\n`;
    report += `   END OF REPORT\n`;
    report += `${bar}\n`;

    if (mode === "append") {
      appendFileSync(filepath, "\n\n" + report);
    } else {
      writeFileSync(filepath, report);
    }

    return {
      filepath,
      summary: {
        total:           findings.length,
        PASS:            counts.PASS,
        FAIL:            counts.FAIL,
        REVIEW:          counts.REVIEW,
        compliance_rate: complianceRate + "%",
        max_utilization: maxUtil ? maxUtil + "%" : null,
        avg_utilization: avgUtil ? avgUtil + "%" : null,
        controlling_check: controllingFinding
          ? `${controllingFinding.design_claim?.parameter} (${maxUtil}%)`
          : null,
      },
    };
  },
};
