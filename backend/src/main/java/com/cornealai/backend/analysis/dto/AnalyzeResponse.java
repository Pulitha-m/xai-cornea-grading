package com.cornealai.backend.analysis.dto;

import java.util.UUID;

/**
 * Mirrors ml-service's response; {@code analysisId} is added by the backend and
 * identifies the stored analysis record.
 */
public record AnalyzeResponse(
        UUID analysisId,
        String caseId,
        String status,
        ImageValidation imageValidation,
        CellularResult cellular,
        GradingResult grading,
        DiseaseResult disease,
        RecommendationResult recommendation
) {

    public AnalyzeResponse withAnalysisId(UUID id) {
        return new AnalyzeResponse(id, caseId, status, imageValidation, cellular, grading, disease, recommendation);
    }
}
