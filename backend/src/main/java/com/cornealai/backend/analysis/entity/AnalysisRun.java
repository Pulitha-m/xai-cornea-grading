package com.cornealai.backend.analysis.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/** One analysis request on an uploaded image, including rejected ones (for audit). */
@Entity
@Table(name = "analysis_runs")
@Getter
@Setter
@NoArgsConstructor
public class AnalysisRun {

    @Id
    private UUID id;

    @Column(name = "image_id", nullable = false)
    private UUID imageId;

    /** The donor case's id as text (never the tissue ID); same value as {@link #donorCaseId}. */
    @Column(name = "case_id", nullable = false, length = 100)
    private String caseId;

    @Column(name = "donor_case_id")
    private UUID donorCaseId;

    @Column(name = "requested_by", nullable = false)
    private Long requestedBy;

    private Double ecd;

    /** "completed", "partial" or "rejected". */
    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "error_code", length = 50)
    private String errorCode;

    @Column(name = "result_json", columnDefinition = "TEXT")
    private String resultJson;

    @Column(name = "clinical_features_json", columnDefinition = "TEXT")
    private String clinicalFeaturesJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
