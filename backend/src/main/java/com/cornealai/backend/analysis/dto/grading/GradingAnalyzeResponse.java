package com.cornealai.backend.analysis.dto.grading;

import com.cornealai.backend.analysis.dto.EcdReference;
import com.cornealai.backend.analysis.dto.FeatureWarning;
import com.cornealai.backend.analysis.dto.ImageValidation;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Mirrors ml-service's POST /grading/analyze response; {@code analysisId} is added by the backend.
 * {@code modelProbabilities} is the share of trees voting for each grade (uncalibrated, not a
 * confidence); {@code ecdReference} is the ECD rule's grade; {@code featuresUsed} echoes the
 * validated 24 features (null = not recorded).
 */
public record GradingAnalyzeResponse(
        UUID analysisId,
        String caseId,
        String status,
        ImageValidation imageValidation,
        String grade,
        String method,
        Map<String, Double> modelProbabilities,
        Map<String, Object> featuresUsed,
        List<String> featuresNotRecorded,
        List<FeatureWarning> warnings,
        EcdReference ecdReference,
        Boolean reviewRequired,
        String message
) {

    public GradingAnalyzeResponse withAnalysisId(UUID id) {
        return new GradingAnalyzeResponse(id, caseId, status, imageValidation, grade, method, modelProbabilities,
                featuresUsed, featuresNotRecorded, warnings, ecdReference, reviewRequired, message);
    }
}
