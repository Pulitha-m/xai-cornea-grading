package com.cornealai.backend.transplant;

import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequestInfo;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.cornealai.backend.analysis.dto.recommendation.MatchWeights;
import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Request and response bodies of /api/transplants: matching from cases, grafts and their follow-up. */
public final class TransplantDtos {

    private TransplantDtos() {
    }

    /** Rank the signed-off corneas in stock for a recipient request. */
    public record CaseMatchRequest(
            @NotNull @Valid MatchRequestInfo request,
            @Pattern(regexp = "ml|mcda") String method,
            @Valid MatchWeights weights,
            @Min(1) @Max(200) Integer topK
    ) {
    }

    /**
     * The ranking (record IDs are case UUIDs) with each case's tissue ID for display, how many corneas
     * were considered and how many signed-off corneas were left out as no longer in stock.
     */
    public record CaseMatchResponse(MatchResponse match, Map<String, String> tissueIds, int considered, int notInStock) {
    }

    /** Allocate a signed-off cornea to a recipient request: this creates its graft record. */
    public record AllocateRequest(
            @NotNull UUID caseId,
            @NotBlank @Size(max = 100) String requestId,
            @NotBlank @Pattern(regexp = "PK|DSEK|DMEK") String procedure,
            @NotBlank @Size(max = 60) String indication,
            LocalDate surgeryDate,
            UUID matchRunId
    ) {
    }

    /** Changes to a graft after allocation (null = unchanged). */
    public record GraftUpdate(
            @Size(min = 1, max = 60) String indication,
            LocalDate surgeryDate,
            Boolean rejectionBy12m
    ) {
    }

    /** Specular microscopy at a follow-up visit (same limits as the follow-up model's inputs). */
    public record VisitRequest(
            @NotNull @DecimalMin(value = "0", inclusive = false) @DecimalMax("5000") Double ecd,
            @NotNull @DecimalMin("0") @DecimalMax("100") Double cv,
            @NotNull @DecimalMin("0") @DecimalMax("100") Double hex,
            LocalDate visitDate
    ) {
    }

    public record VisitView(int month, double ecd, double cv, double hex, LocalDate visitDate) {
    }

    public record FollowupSummary(UUID runId, String status, String errorCode, String alert, Integer nextVisitMonths,
                                  Instant createdAt) {
    }

    /**
     * A graft with what the follow-up model needs: donor age and baseline endothelium (from the
     * sign-off, else the case details) and the recorded visits; {@code missing} lists what is still needed.
     */
    public record GraftView(
            UUID id,
            UUID caseId,
            String tissueId,
            String requestId,
            String procedure,
            String indication,
            LocalDate surgeryDate,
            Boolean rejectionBy12m,
            Double donorAge,
            Double baselineEcd,
            Double baselineCv,
            Double baselineHex,
            List<VisitView> visits,
            List<String> missing,
            FollowupSummary latestFollowup,
            Instant createdAt
    ) {
    }

    /** A follow-up recommendation with the request it was made from (for the report's charts). */
    public record GraftFollowup(FollowupSummary summary, FollowupRequest request, FollowupResponse result) {
    }
}
