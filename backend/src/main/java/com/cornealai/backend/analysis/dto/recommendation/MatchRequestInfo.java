package com.cornealai.backend.analysis.dto.recommendation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * The recipient request: study code (Q + 4 digits, e.g. Q0012), requested grade, planned surgery and urgency.
 * Study codes keep real NEBSL identifiers out of the ML service and the stored runs. Leave {@code requestId}
 * empty for a new request: the backend assigns the next free code; send it again to re-rank that request.
 */
public record MatchRequestInfo(
        @Pattern(regexp = "Q[0-9]{4}", message = "must be Q followed by 4 digits, e.g. Q0012") String requestId,
        @NotBlank @Pattern(regexp = "A\\+|A|B|C") String requestedGrade,
        @Size(max = 30) String surgeryType,
        @Pattern(regexp = "Routine|Emergency") String urgency
) {
}
