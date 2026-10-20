package com.cornealai.backend.analysis.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/**
 * A result image of a run (overlay, Grad-CAM or image map), stored encrypted at {@code objectPath}.
 * {@code jsonPath} (a JSON Pointer) is where it goes back into the run's stored result.
 */
@Entity
@Table(name = "run_artifacts")
@Getter
@Setter
@NoArgsConstructor
public class RunArtifact {

    @Id
    private UUID id;

    @Column(nullable = false, length = 20)
    private String module;

    @Column(name = "run_id", nullable = false)
    private UUID runId;

    @Column(name = "donor_case_id", nullable = false)
    private UUID donorCaseId;

    @Column(name = "json_path", nullable = false, length = 200)
    private String jsonPath;

    @Column(name = "content_type", nullable = false, length = 50)
    private String contentType;

    @Column(name = "object_path", nullable = false, length = 300)
    private String objectPath;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
