package com.cornealai.backend.analysis.dto.disease;

import java.util.List;

/**
 * Effect of the five CellChek values on one output with the image fixed:
 * {@code baseline} (all values at their training median) + sum of contributions = {@code prediction}.
 */
public record ShapExplanation(Double baseline, Double prediction, List<ShapValue> values) {
}
