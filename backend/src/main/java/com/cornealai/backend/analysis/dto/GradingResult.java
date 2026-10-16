package com.cornealai.backend.analysis.dto;

import java.util.List;
import java.util.Map;

/**
 * Grade from the hybrid model (24 features + image). {@code modelProbabilities} is the share of trees voting
 * for each grade (uncalibrated, not a confidence); {@code ecdReference} is the ECD rule's grade.
 */
public record GradingResult(
        String status,
        String error,
        String grade,
        String method,
        Map<String, Double> modelProbabilities,
        List<String> featuresNotRecorded,
        List<FeatureWarning> warnings,
        EcdReference ecdReference,
        Boolean reviewRequired,
        String message
) {
}
