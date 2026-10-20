package com.cornealai.backend.cases.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * One donor cornea. The {@code *Enc} fields hold {@link com.cornealai.backend.common.crypto.FieldCipher}
 * ciphertext, encrypted for the field names below and this row's id, so the id must be set first.
 * Never log or return these fields without decrypting them for an authorised caller.
 */
@Entity
@Table(name = "donor_cases")
@Getter
@Setter
@NoArgsConstructor
public class DonorCase {

    /** Field names bound into each encrypted value (FieldCipher) and the blind index (BlindIndex). */
    public static final String TISSUE_NUMBER = "donor_cases.tissue_number_enc";
    public static final String DONOR_IDENTITY = "donor_cases.donor_identity_enc";
    public static final String CAUSE_OF_DEATH = "donor_cases.cause_of_death_enc";
    public static final String MEDICAL_HISTORY = "donor_cases.medical_history_enc";
    public static final String SEROLOGY = "donor_cases.serology_enc";
    public static final String CLINICAL_NOTES = "donor_cases.clinical_notes_enc";
    public static final String TISSUE_NUMBER_INDEX = "donor_cases.tissue_number";

    @Id
    private UUID id;

    @Column(name = "tissue_number_enc", nullable = false)
    private byte[] tissueNumberEnc;

    @Column(name = "tissue_number_bidx", nullable = false, length = 64)
    private String tissueNumberBidx;

    @Column(name = "donor_identity_enc")
    private byte[] donorIdentityEnc;

    @Column(name = "cause_of_death_enc")
    private byte[] causeOfDeathEnc;

    @Column(name = "medical_history_enc")
    private byte[] medicalHistoryEnc;

    @Column(name = "serology_enc")
    private byte[] serologyEnc;

    @Column(name = "clinical_notes_enc")
    private byte[] clinicalNotesEnc;

    /** False when any serology result is positive; null when not all are known. Restricted (health data). */
    @Column(name = "serology_clear")
    private Boolean serologyClear;

    @Column(name = "donor_age_years")
    private Integer donorAgeYears;

    @Column(name = "death_to_preservation_hours")
    private Double deathToPreservationHours;

    @Column(name = "preservation_date")
    private LocalDate preservationDate;

    private Double ecd;

    private Double cv;

    @Column(name = "hex_percent")
    private Double hexPercent;

    private Double sd;

    @Column(name = "total_cell_count")
    private Integer totalCellCount;

    @Column(name = "total_area_um2")
    private Double totalAreaUm2;

    /** The slit-lamp findings of the grading feature schema, as JSON (not identifying). */
    @Column(name = "slit_lamp_json", columnDefinition = "TEXT")
    private String slitLampJson;

    @Column(name = "created_by", nullable = false, updatable = false)
    private Long createdBy;

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
