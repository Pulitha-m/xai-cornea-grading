package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** The recipient request: study code, requested grade, planned surgery and urgency. */
public record MatchRequestInfo(
        @NotBlank @Size(max = 100) String requestId,
        @NotBlank @Pattern(regexp = "A\\+|A|B|C") String requestedGrade,
        @Size(max = 30) String surgeryType,
        @Pattern(regexp = "Routine|Emergency") String urgency
) {
}
