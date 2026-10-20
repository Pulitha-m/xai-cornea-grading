package com.cornealai.backend.analysis.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/**
 * One recommendation request, including rejected ones (for audit): a donor-tissue ranking ("match") for a
 * recipient request, or a follow-up recommendation ("followup") for a graft at its 12-month visit.
 */
@Entity
@Table(name = "recommendation_runs")
@Getter
@Setter
@NoArgsConstructor
public class RecommendationAnalysisRun {

    public static final String MATCH = "match";
    public static final String FOLLOWUP = "followup";

    @Id
    private UUID id;

    /** "match" or "followup". */
    @Column(nullable = false, length = 20)
    private String kind;

    /** Study code of the recipient request (match) or of the graft (followup). */
    @Column(name = "subject_id", nullable = false, length = 100)
    private String subjectId;

    @Column(name = "requested_by", nullable = false)
    private Long requestedBy;

    /** "completed" or "rejected". */
    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "error_code", length = 50)
    private String errorCode;

    /** match: "ml" or "mcda". */
    @Column(name = "method_used", length = 50)
    private String methodUsed;

    /** match: study code of the cornea ranked #1. */
    @Column(name = "top_record_id", length = 100)
    private String topRecordId;

    /** followup: "green", "amber" or "red". */
    @Column(length = 10)
    private String alert;

    /** followup: recommended interval to the next visit. */
    @Column(name = "next_visit_months")
    private Integer nextVisitMonths;

    /** The full response. */
    @Column(name = "result_json", columnDefinition = "TEXT")
    private String resultJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
