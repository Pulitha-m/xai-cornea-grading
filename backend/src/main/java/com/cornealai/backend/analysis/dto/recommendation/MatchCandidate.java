package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * One cornea in stock, by its study code (R + 4 digits). Corneas from donor cases are sent by their case ID
 * by the transplant service, which builds this record itself. Missing values are allowed (null) and handled
 * by the model. The upper limits reject impossible values; possible but unusual values are returned as
 * warnings by the ml-service.
 */
public record MatchCandidate(
        @NotBlank @Pattern(regexp = "R[0-9]{4}|" + RecommendationIds.UUID,
                message = "must be the study code R followed by 4 digits, e.g. R0012 (not the NEBSL tissue ID)") String recordId,
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
