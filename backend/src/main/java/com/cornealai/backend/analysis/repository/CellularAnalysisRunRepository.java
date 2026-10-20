package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.CellularAnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface CellularAnalysisRunRepository extends JpaRepository<CellularAnalysisRun, UUID> {

    List<CellularAnalysisRun> findByImageId(UUID imageId);

    List<CellularAnalysisRun> findByDonorCaseIdOrderByCreatedAtDesc(UUID donorCaseId);

    /** Runs of any case older than {@code before}, newest first (keyset paging). */
    List<CellularAnalysisRun> findByDonorCaseIdIsNotNullAndCreatedAtBeforeOrderByCreatedAtDesc(java.time.Instant before,
            org.springframework.data.domain.Pageable page);

    List<CellularAnalysisRun> findByDonorCaseIdAndCreatedAtBeforeOrderByCreatedAtDesc(UUID donorCaseId, java.time.Instant before,
            org.springframework.data.domain.Pageable page);
}
