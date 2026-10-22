package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * A graft at its 12-month visit: donor values, the 3-, 6- and 12-month specular microscopy (the 3-month
 * visit may be missing) and whether a rejection episode occurred in the first year.
 */
public record FollowupRequest(
        @NotBlank @Size(max = 100) String graftId,
        @NotBlank @Pattern(regexp = "PK|DSEK|DMEK") String procedure,
        @NotBlank @Pattern(regexp = "Fuchs/Endothelial|Bullous keratopathy|Failed/Re-graft|Other") String indication,
        @NotNull @DecimalMin("0") @DecimalMax("100") Double donorAge,
        @NotNull @DecimalMin(value = "0", inclusive = false) @DecimalMax("5000") Double baselineEcd,
        @NotNull @DecimalMin("0") @DecimalMax("100") Double baselineCv,
        @NotNull @DecimalMin("0") @DecimalMax("100") Double baselineHex,
        @Valid FollowupVisit visit3m,
        @NotNull @Valid FollowupVisit visit6m,
        @NotNull @Valid FollowupVisit visit12m,
        Boolean rejectionBy12m
) {
}
