package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

/** Specular microscopy at one follow-up visit. */
public record FollowupVisit(
        @NotNull @DecimalMin(value = "0", inclusive = false) @DecimalMax("5000") Double ecd,
        @NotNull @DecimalMin("0") @DecimalMax("100") Double cv,
        @NotNull @DecimalMin("0") @DecimalMax("100") Double hex
) {
}
