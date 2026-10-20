package com.cornealai.backend.cases.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/**
 * What a specialist confirmed for a case. Append-only: a correction is a new sign-off, and the newest
 * is the current one. {@code notesEnc} is FieldCipher ciphertext (free text may identify someone).
 */
@Entity
@Table(name = "case_signoffs")
@Getter
@Setter
@NoArgsConstructor
public class CaseSignoff {

    public static final String NOTES = "case_signoffs.notes_enc";

    @Id
    private UUID id;

    @Column(name = "donor_case_id", nullable = false, updatable = false)
    private UUID donorCaseId;

    /** The case analysis the specialist reviewed, if any. */
    @Column(name = "case_analysis_id", updatable = false)
    private UUID caseAnalysisId;

    @Column(name = "signed_by", nullable = false, updatable = false)
    private Long signedBy;

    @Column(name = "confirmed_grade", nullable = false, length = 5, updatable = false)
    private String confirmedGrade;

    @Column(name = "disease_finding", nullable = false, length = 20, updatable = false)
    private String diseaseFinding;

    @Column(updatable = false)
    private Double ecd;

    @Column(updatable = false)
    private Double cv;

    @Column(name = "hex_percent", updatable = false)
    private Double hexPercent;

    @Column(name = "notes_enc", updatable = false)
    private byte[] notesEnc;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
