package com.cornealai.backend.analysis.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/** One donor cornea grading request on an uploaded image, including rejected ones (for audit). */
@Entity
@Table(name = "grading_analysis_runs")
@Getter
@Setter
@NoArgsConstructor
public class GradingAnalysisRun {

    @Id
    private UUID id;

    @Column(name = "image_id", nullable = false)
    private UUID imageId;

    @Column(name = "case_id", nullable = false, length = 100)
    private String caseId;

    @Column(name = "requested_by", nullable = false)
    private Long requestedBy;

    /** "completed" or "rejected". */
    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "error_code", length = 50)
    private String errorCode;

    private Double ecd;

    /** The hybrid model's grade; null when rejected. */
    @Column(length = 10)
    private String grade;

    @Column(name = "clinical_features_json", columnDefinition = "TEXT")
    private String clinicalFeaturesJson;

    @Column(name = "result_json", columnDefinition = "TEXT")
    private String resultJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
