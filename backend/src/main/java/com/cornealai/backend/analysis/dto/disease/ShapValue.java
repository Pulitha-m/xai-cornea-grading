package com.cornealai.backend.analysis.dto.disease;

/**
 * One CellChek value's exact Shapley contribution, in probability units. {@code imputed} = not
 * recorded (the training median was used, so the contribution is 0). ECD includes ECD_Deficit.
 */
public record ShapValue(String input, Double value, Boolean imputed, Double contribution) {
}
