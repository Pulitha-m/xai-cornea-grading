package com.cornealai.backend.cases.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/** One analysis request on a donor case; each module's run links back here (case_analysis_id). */
@Entity
@Table(name = "case_analyses")
@Getter
@Setter
@NoArgsConstructor
public class CaseAnalysis {

    @Id
    private UUID id;

    @Column(name = "donor_case_id", nullable = false)
    private UUID donorCaseId;

    @Column(name = "image_id", nullable = false)
    private UUID imageId;

    @Column(name = "requested_by", nullable = false)
    private Long requestedBy;

    /** Comma-separated module names, in the order they ran. */
    @Column(nullable = false, length = 100)
    private String modules;

    @Column(name = "consistency_json", columnDefinition = "TEXT")
    private String consistencyJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
