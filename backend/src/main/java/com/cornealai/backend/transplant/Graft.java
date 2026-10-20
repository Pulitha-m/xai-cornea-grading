package com.cornealai.backend.transplant;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * A transplanted cornea: a signed-off donor case allocated to a recipient request. One per cornea.
 * {@code requestId} is the request's study code, never a recipient name or hospital number.
 */
@Entity
@Table(name = "grafts")
@Getter
@Setter
@NoArgsConstructor
public class Graft {

    @Id
    private UUID id;

    @Column(name = "donor_case_id", nullable = false, updatable = false)
    private UUID donorCaseId;

    @Column(name = "request_id", nullable = false, length = 100)
    private String requestId;

    /** PK, DSEK or DMEK. */
    @Column(name = "procedure_type", nullable = false, length = 10)
    private String procedure;

    @Column(nullable = false, length = 60)
    private String indication;

    @Column(name = "surgery_date")
    private LocalDate surgeryDate;

    /** Whether a rejection episode occurred in the first year (null = not yet known). */
    @Column(name = "rejection_by_12m")
    private Boolean rejectionBy12m;

    /** The matching run that ranked this cornea for the request, if any. */
    @Column(name = "match_run_id", updatable = false)
    private UUID matchRunId;

    @Column(name = "allocated_by", nullable = false, updatable = false)
    private Long allocatedBy;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
        updatedAt = createdAt;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }
}
