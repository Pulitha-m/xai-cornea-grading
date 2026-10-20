package com.cornealai.backend.transplant;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/** Specular microscopy of a graft at its 3-, 6- or 12-month follow-up visit. */
@Entity
@Table(name = "graft_visits")
@Getter
@Setter
@NoArgsConstructor
public class GraftVisit {

    @Id
    private UUID id;

    @Column(name = "graft_id", nullable = false, updatable = false)
    private UUID graftId;

    @Column(name = "visit_month", nullable = false, updatable = false)
    private int month;

    @Column(nullable = false)
    private double ecd;

    @Column(nullable = false)
    private double cv;

    @Column(nullable = false)
    private double hex;

    @Column(name = "visit_date")
    private LocalDate visitDate;

    @Column(name = "recorded_by", nullable = false)
    private Long recordedBy;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    @PreUpdate
    void touch() {
        updatedAt = Instant.now();
    }
}
