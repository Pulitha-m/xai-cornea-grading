package com.cornealai.backend.analysis.dto.recommendation;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Mirrors ml-service's POST /recommendation/match response; {@code analysisId} is added by the backend.
 * Positive-serology corneas are never ranked: they are listed in {@code excluded}.
 */
public record MatchResponse(
        UUID analysisId,
        String requestId,
        List<RankedCandidate> ranked,
        List<ExcludedCandidate> excluded,
        Map<String, Double> weightsUsed,
        Boolean endotheliumConsidered,
        String methodUsed,
        String model,
        Map<String, Object> modelSummary,
        String disclaimer
) {

    public MatchResponse withAnalysisId(UUID id) {
        return new MatchResponse(id, requestId, ranked, excluded, weightsUsed, endotheliumConsidered, methodUsed,
                model, modelSummary, disclaimer);
    }
}
