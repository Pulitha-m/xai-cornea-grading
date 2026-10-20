package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.GradingAnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface GradingAnalysisRunRepository extends JpaRepository<GradingAnalysisRun, UUID> {

    List<GradingAnalysisRun> findByImageId(UUID imageId);

    List<GradingAnalysisRun> findByDonorCaseIdOrderByCreatedAtDesc(UUID donorCaseId);

    /** Runs of any case older than {@code before}, newest first (keyset paging). */
    List<GradingAnalysisRun> findByDonorCaseIdIsNotNullAndCreatedAtBeforeOrderByCreatedAtDesc(java.time.Instant before,
            org.springframework.data.domain.Pageable page);

    List<GradingAnalysisRun> findByDonorCaseIdAndCreatedAtBeforeOrderByCreatedAtDesc(UUID donorCaseId, java.time.Instant before,
            org.springframework.data.domain.Pageable page);
}
