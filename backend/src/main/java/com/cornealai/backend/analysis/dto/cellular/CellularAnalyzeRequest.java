package com.cornealai.backend.analysis.dto.cellular;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.UUID;

/** Cellular analysis (ROI, cells, ECD / CV / HEX) of a previously uploaded image (id from POST /api/analysis/images). */
public record CellularAnalyzeRequest(
        @NotBlank @Size(max = 100) String caseId,
        @NotNull UUID imageId
) {
}
