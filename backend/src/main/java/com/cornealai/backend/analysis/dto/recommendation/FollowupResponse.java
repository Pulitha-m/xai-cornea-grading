package com.cornealai.backend.analysis.dto.recommendation;

import java.util.List;
import java.util.UUID;

/**
 * Mirrors ml-service's POST /recommendation/followup response; {@code analysisId} is added by the backend.
 * {@code actions} are review prompts, not treatment instructions; {@code counterfactuals} are descriptive.
 */
public record FollowupResponse(
        UUID analysisId,
        String graftId,
        String alert,
        Integer nextVisitMonths,
        List<String> rulesFired,
        List<String> actions,
        List<PredictedEcd> predictedEcd,
        String bandLevel,
        List<RiskEstimate> risk,
        FollowupReasons reasons,
        List<String> counterfactuals,
        String model,
        String modelVersion,
        String rulesVersion,
        String dataSource,
        String disclaimer
) {

    public FollowupResponse withAnalysisId(UUID id) {
        return new FollowupResponse(id, graftId, alert, nextVisitMonths, rulesFired, actions, predictedEcd, bandLevel,
                risk, reasons, counterfactuals, model, modelVersion, rulesVersion, dataSource, disclaimer);
    }
}
