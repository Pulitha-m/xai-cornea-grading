package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.AnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface AnalysisRunRepository extends JpaRepository<AnalysisRun, UUID> {

    List<AnalysisRun> findByImageId(UUID imageId);

    List<AnalysisRun> findByDonorCaseIdOrderByCreatedAtDesc(UUID donorCaseId);

    /** Runs of any case older than {@code before}, newest first (keyset paging). */
    List<AnalysisRun> findByDonorCaseIdIsNotNullAndCreatedAtBeforeOrderByCreatedAtDesc(java.time.Instant before,
            org.springframework.data.domain.Pageable page);

    List<AnalysisRun> findByDonorCaseIdAndCreatedAtBeforeOrderByCreatedAtDesc(UUID donorCaseId, java.time.Instant before,
            org.springframework.data.domain.Pageable page);
}
