package com.cornealai.backend.analysis.dto;

public record RecommendationResult(
        String status,
        String error,
        String recommendation,
        Double confidence
) {
}