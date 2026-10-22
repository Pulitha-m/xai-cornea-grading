package com.cornealai.backend.analysis.dto.recommendation;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Mirrors ml-service's POST /recommendation/followup response; {@code analysisId} is added by the backend.
 * {@code actions} are review prompts, not treatment instructions; {@code counterfactuals} are descriptive.
 * {@code warnings} lists possible but unusual values to check; they do not change the recommendation.
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
        Map<String, Double> alertThresholds,
        Map<String, Object> modelSummary,
        String model,
        String modelVersion,
        String rulesVersion,
        String dataSource,
        String disclaimer,
        List<String> warnings
) {

    /** Without warnings (callers that build a response themselves). */
    public FollowupResponse(UUID analysisId, String graftId, String alert, Integer nextVisitMonths,
                            List<String> rulesFired, List<String> actions, List<PredictedEcd> predictedEcd,
                            String bandLevel, List<RiskEstimate> risk, FollowupReasons reasons,
                            List<String> counterfactuals, Map<String, Double> alertThresholds,
                            Map<String, Object> modelSummary, String model, String modelVersion,
                            String rulesVersion, String dataSource, String disclaimer) {
        this(analysisId, graftId, alert, nextVisitMonths, rulesFired, actions, predictedEcd, bandLevel, risk, reasons,
                counterfactuals, alertThresholds, modelSummary, model, modelVersion, rulesVersion, dataSource,
                disclaimer, List.of());
    }

    public FollowupResponse withAnalysisId(UUID id) {
        return new FollowupResponse(id, graftId, alert, nextVisitMonths, rulesFired, actions, predictedEcd, bandLevel,
                risk, reasons, counterfactuals, alertThresholds, modelSummary, model, modelVersion, rulesVersion,
                dataSource, disclaimer, warnings == null ? List.of() : warnings);
    }
}
