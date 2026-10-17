package com.cornealai.backend.analysis.dto.disease;

/** Image quality measures and the unusual-image distance with the limits they were judged against. */
public record ImageQuality(
        String rating,
        Double focus,
        Double focusLowLimit,
        Double darkFraction,
        Double saturatedFraction,
        Double contrast,
        Double unusualDistance,
        Double unusualWarnAbove,
        Double unusualRejectAbove
) {
}
