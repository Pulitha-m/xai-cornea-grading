package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;

/**
 * Donor-tissue ranking for one recipient request: the request and the corneas currently in stock.
 * {@code method} is "ml" (trained ranker, default) or "mcda" (rule-based baseline).
 */
public record MatchRequest(
        @NotNull @Valid MatchRequestInfo request,
        @NotEmpty @Size(max = 200) List<@Valid MatchCandidate> candidates,
        @Min(1) @Max(200) Integer topK,
        @Valid MatchWeights weights,
        @Pattern(regexp = "ml|mcda") String method
) {
}
