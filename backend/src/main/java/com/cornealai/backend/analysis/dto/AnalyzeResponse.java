package com.cornealai.backend.analysis.dto;

public record AnalyzeResponse(
        String caseId,
        String status,
        CellularResult cellular,
        GradingResult grading,
        DiseaseResult disease,
        RecommendationResult recommendation
) {
}