package com.cornealai.backend.analysis.dto.grading;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.Map;
import java.util.UUID;

/**
 * Grading of a previously uploaded image (id from POST /api/analysis/images). {@code clinicalFeatures}
 * holds the 24 model features by name (null = not recorded); ml-service validates them against the
 * training schema.
 */
public record GradingAnalyzeRequest(
        @NotBlank @Size(max = 100) String caseId,
        @NotNull UUID imageId,
        @NotNull @Size(max = 24) Map<String, Object> clinicalFeatures
) {
}
