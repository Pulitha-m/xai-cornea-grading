package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.constraints.DecimalMin;

/** Optional clinician-set MCDA weights; a null field keeps its default. */
public record MatchWeights(
        @DecimalMin("0") Double gradeFit,
        @DecimalMin("0") Double endothelium,
        @DecimalMin("0") Double serology,
        @DecimalMin("0") Double freshness,
        @DecimalMin("0") Double surgeryCompatibility
) {
}
