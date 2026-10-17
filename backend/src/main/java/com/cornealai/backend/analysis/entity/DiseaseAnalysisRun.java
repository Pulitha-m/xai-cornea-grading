package com.cornealai.backend.analysis.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/** One v2 disease detection + severity request on an uploaded image, including rejected ones (for audit). */
@Entity
@Table(name = "disease_analysis_runs")
@Getter
@Setter
@NoArgsConstructor
public class DiseaseAnalysisRun {

    @Id
    private UUID id;

    @Column(name = "image_id", nullable = false)
    private UUID imageId;

    @Column(name = "case_id", nullable = false, length = 100)
    private String caseId;

    @Column(name = "requested_by", nullable = false)
    private Long requestedBy;

    /** "completed", "input_check_failed" or "rejected". */
    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "error_code", length = 50)
    private String errorCode;

    /** The analysis was requested despite failed input checks. */
    @Column(nullable = false)
    private boolean forced;

    @Column(name = "measurements_json", columnDefinition = "TEXT")
    private String measurementsJson;

    /** The response without Grad-CAM images. */
    @Column(name = "result_json", columnDefinition = "TEXT")
    private String resultJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
