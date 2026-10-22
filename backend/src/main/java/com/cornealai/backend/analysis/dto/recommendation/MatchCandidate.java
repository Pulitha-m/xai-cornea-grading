package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * One cornea in stock. Missing values are allowed (null) and handled by the model. The upper limits reject
 * impossible values; possible but unusual values are returned as warnings by the ml-service.
 */
public record MatchCandidate(
        @NotBlank @Size(max = 100) String recordId,
        @Pattern(regexp = "A\\+|A|B|C") String grade,
        @DecimalMin("0") @DecimalMax("5000") Double ecd,
        @DecimalMin("0") @DecimalMax("100") Double cv,
        @DecimalMin("0") @DecimalMax("100") Double hex,
        @DecimalMin("0") @DecimalMax("100") Double donorAge,
        @DecimalMin("0") @DecimalMax("72") Double deathToPreservationH,
        @DecimalMin("0") @DecimalMax("60") Double daysInStorage,
        @Pattern(regexp = "Yes|No|Unknown") String serologyClear
) {
}
