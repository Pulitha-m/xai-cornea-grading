package com.cornealai.backend.analysis.dto;

/** Result of ml-service's image checks; only images that pass reach the analysis modules. */
public record ImageValidation(
        String domainStatus,
        Boolean qualityAssessed,
        Integer width,
        Integer height,
        String format
) {
}
