package com.cornealai.backend.analysis.dto;

import java.util.UUID;

/** Reference to a stored image. The storage location itself is never returned to clients. */
public record ImageUploadResponse(
        UUID imageId,
        String caseId,
        String contentType,
        long sizeBytes,
        int width,
        int height
) {
}
