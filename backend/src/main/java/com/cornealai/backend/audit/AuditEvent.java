package com.cornealai.backend.audit;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/** One audited action: who decrypted or changed what, and when. Never holds the sensitive value itself. */
@Entity
@Table(name = "audit_events")
@Getter
@Setter
@NoArgsConstructor
public class AuditEvent {

    @Id
    private UUID id;

    @Column(name = "occurred_at", nullable = false, updatable = false)
    private Instant occurredAt;

    @Column(name = "user_id", nullable = false, updatable = false)
    private Long userId;

    @Column(nullable = false, length = 40, updatable = false)
    private String action;

    @Column(name = "subject_type", length = 30, updatable = false)
    private String subjectType;

    @Column(name = "subject_id", updatable = false)
    private UUID subjectId;

    @Column(length = 200, updatable = false)
    private String detail;
}
