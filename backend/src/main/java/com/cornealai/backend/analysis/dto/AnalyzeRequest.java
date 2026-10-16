package com.cornealai.backend.analysis.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.Map;
import java.util.UUID;

/**
 * Analysis of a previously uploaded image. The image is referenced by the id returned
 * from the upload endpoint, never by a client-supplied URL. {@code clinicalFeatures}
 * holds the 24 model features by name (null = not recorded); ml-service validates them
 * against the training schema.
 */
public record AnalyzeRequest(
        @NotBlank @Size(max = 100) String caseId,
        @NotNull UUID imageId,
        @NotNull @Size(max = 24) Map<String, Object> clinicalFeatures
) {
}
