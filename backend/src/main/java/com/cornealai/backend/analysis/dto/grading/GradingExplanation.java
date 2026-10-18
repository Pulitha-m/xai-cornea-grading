package com.cornealai.backend.analysis.dto.grading;

import java.util.List;

/**
 * TreeSHAP explanation of the predicted grade: {@code baseline} (training average share of tree votes)
 * plus every feature's and the image's contribution equals {@code prediction}. Explains the model, not the cornea.
 */
public record GradingExplanation(
        String method,
        String explainedGrade,
        Double baseline,
        Double prediction,
        List<FeatureContribution> features,
        Double imageContribution,
        ImageAttributionMap imageMap,
        String message
) {

    public GradingExplanation withoutImageMaps() {
        return new GradingExplanation(method, explainedGrade, baseline, prediction, features, imageContribution,
                imageMap == null ? null : imageMap.withoutImages(), message);
    }
}
