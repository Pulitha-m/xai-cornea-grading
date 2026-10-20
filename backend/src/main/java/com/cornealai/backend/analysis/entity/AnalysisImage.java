package com.cornealai.backend.analysis.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/**
 * An uploaded specular microscopy image. The bytes live in Supabase Storage at {@code bucket/objectPath},
 * encrypted (see {@link com.cornealai.backend.analysis.service.ImageService}).
 */
@Entity
@Table(name = "analysis_images")
@Getter
@Setter
@NoArgsConstructor
public class AnalysisImage {

    @Id
    private UUID id;

    /** The donor case's id as text (never the tissue ID); same value as {@link #donorCaseId}. */
    @Column(name = "case_id", nullable = false, length = 100)
    private String caseId;

    @Column(name = "donor_case_id")
    private UUID donorCaseId;

    @Column(nullable = false, length = 100)
    private String bucket;

    @Column(name = "object_path", nullable = false, length = 300)
    private String objectPath;

    @Column(name = "content_type", nullable = false, length = 50)
    private String contentType;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    /** SHA-256 of the plaintext; only for images stored before encryption (null once encrypted). */
    @Column(length = 64)
    private String sha256;

    /** True when the stored object is FieldCipher ciphertext; false only for images stored before encryption. */
    @Column(nullable = false)
    private boolean encrypted;

    @Column(nullable = false)
    private int width;

    @Column(nullable = false)
    private int height;

    @Column(name = "uploaded_by", nullable = false)
    private Long uploadedBy;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() {
        createdAt = Instant.now();
    }
}
