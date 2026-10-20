package com.cornealai.backend.analysis.dto.cellular;

/** A warning for the reviewer: level "error" = biomarkers not reliable, "warning" = check. */
public record QualityFlag(
        String level,
        String code,
        String message
) {
}
