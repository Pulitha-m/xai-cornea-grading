package com.cornealai.backend.analysis.dto.disease;

import java.util.List;

/** Severity (Mild or Mod/Sev) of one detected disease group. */
public record SeverityFinding(
        String group,
        String label,
        List<String> diseases,
        String grade,
        Double probability,
        Double threshold,
        String method,
        ShapExplanation shap
) {
}
