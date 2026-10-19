package com.cornealai.backend.analysis.dto.cellular;

/** Measured cells by reliability level (red = implausible size / shape, yellow = low confidence, green otherwise). */
public record CellularReliability(
        String rule,
        Integer green,
        Integer yellow,
        Integer red,
        Double medianConfidence
) {
}
