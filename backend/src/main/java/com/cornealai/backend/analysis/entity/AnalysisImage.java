package com.cornealai.backend.analysis.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.UUID;

/** An uploaded specular microscopy image. The bytes live in Supabase Storage at {@code bucket/objectPath}. */
@Entity
@Table(name = "analysis_images")
@Getter
@Setter
@NoArgsConstructor
public class AnalysisImage {

    @Id
    private UUID id;

    @Column(name = "case_id", nullable = false, length = 100)
    private String caseId;

    @Column(nullable = false, length = 100)
    private String bucket;

    @Column(name = "object_path", nullable = false, length = 300)
    private String objectPath;

    @Column(name = "content_type", nullable = false, length = 50)
    private String contentType;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    @Column(nullable = false, length = 64)
    private String sha256;

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
