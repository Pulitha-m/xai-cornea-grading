package com.cornealai.backend.analysis.dto.recommendation;

import java.util.List;
import java.util.Map;

/** One ranked cornea: scores, the MCDA reasons, the trained model's "why" and a descriptive counterfactual. */
public record RankedCandidate(
        Integer rank,
        String recordId,
        String grade,
        Double mlScore,
        Double matchScore,
        Integer mcdaRank,
        Integer gradeGap,
        Map<String, Double> criterionScores,
        List<String> reasons,
        List<ReasonEffect> why,
        String whyText,
        String counterfactual,
        List<String> flags
) {
}
