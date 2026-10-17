package com.cornealai.backend.analysis.dto.grading;

/** One input's SHAP contribution to the explained grade; {@code value} as given to the model (null = not recorded). */
public record FeatureContribution(String name, Object value, Double contribution) {
}
