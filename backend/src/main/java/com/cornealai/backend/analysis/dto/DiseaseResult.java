package com.cornealai.backend.analysis.dto;

public record DiseaseResult(
        String status,
        String error,
        String disease,
        String severity,
        Double confidence
) {
}