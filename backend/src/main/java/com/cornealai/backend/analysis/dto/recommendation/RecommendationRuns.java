package com.cornealai.backend.analysis.dto.recommendation;

import tools.jackson.databind.JsonNode;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** Saved recommendation runs, for the "Previous runs" list on the matching and follow-up pages. */
public final class RecommendationRuns {

    private RecommendationRuns() {
    }

    /**
     * One saved run. {@code subjectId} is the request ID (matching) or graft ID (follow-up);
     * {@code topRecordId} is the cornea ranked #1, {@code alert} and {@code nextVisitMonths} the follow-up outcome.
     */
    public record RunSummary(
            UUID id,
            String kind,
            String subjectId,
            String status,
            String errorCode,
            String methodUsed,
            String topRecordId,
            String alert,
            Integer nextVisitMonths,
            String requestedBy,
            Instant createdAt
    ) {
    }

    /** Newest first; pass {@code nextBefore} as {@code before} for older runs (null when there are none). */
    public record RunPage(List<RunSummary> items, Instant nextBefore) {
    }

    /** A saved run with the request it was given and the stored result (null for runs that did not complete). */
    public record RunDetail(RunSummary summary, JsonNode inputs, JsonNode result) {
    }
}
