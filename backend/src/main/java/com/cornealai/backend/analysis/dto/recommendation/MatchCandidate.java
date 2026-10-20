package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** One cornea in stock. Missing values are allowed (null) and handled by the model. */
public record MatchCandidate(
        @NotBlank @Size(max = 100) String recordId,
        @Pattern(regexp = "A\\+|A|B|C") String grade,
        @DecimalMin("0") Double ecd,
        @DecimalMin("0") Double cv,
        @DecimalMin("0") @DecimalMax("100") Double hex,
        @DecimalMin("0") Double donorAge,
        @DecimalMin("0") Double deathToPreservationH,
        @DecimalMin("0") Double daysInStorage,
        @Pattern(regexp = "Yes|No|Unknown") String serologyClear
) {
}
