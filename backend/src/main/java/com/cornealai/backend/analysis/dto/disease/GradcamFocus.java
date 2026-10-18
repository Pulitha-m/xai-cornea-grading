package com.cornealai.backend.analysis.dto.disease;

/** Where a Grad-CAM map is hottest (e.g. "lower right") and the share of the image it highlights. */
public record GradcamFocus(String region, Double coverage) {
}
