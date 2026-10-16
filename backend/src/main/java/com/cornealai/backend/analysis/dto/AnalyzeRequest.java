package com.cornealai.backend.analysis.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.UUID;

/**
 * Analysis of a previously uploaded image. The image is referenced by the id
 * returned from the upload endpoint, never by a client-supplied URL.
 */
public record AnalyzeRequest(
        @NotBlank @Size(max = 100) String caseId,
        @NotNull UUID imageId,
        @DecimalMin(value = "0", inclusive = false) @DecimalMax(value = "6000") Double ecd
) {
}
