package com.cornealai.backend.analysis.dto.disease;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.Map;
import java.util.UUID;

/**
 * v2 disease analysis of a previously uploaded image (id from POST /api/analysis/images).
 * {@code measurements} holds the five CellChek values by name (ECD_CD_cells_per_mm2, SD, CV,
 * HEX_percent, Donor_Age; null = not recorded, never 0); ml-service validates them.
 * {@code force} runs the models even if the input checks fail (the result is marked not reliable).
 */
public record DiseaseAnalyzeRequest(
        @NotBlank @Size(max = 100) String caseId,
        @NotNull UUID imageId,
        @NotNull @Size(max = 5) Map<String, Object> measurements,
        boolean force
) {
}
