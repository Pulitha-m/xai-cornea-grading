package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.RecommendationAnalysisRun;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface RecommendationAnalysisRunRepository extends JpaRepository<RecommendationAnalysisRun, UUID> {

    List<RecommendationAnalysisRun> findBySubjectId(String subjectId);

    List<RecommendationAnalysisRun> findBySubjectIdAndKindOrderByCreatedAtDesc(String subjectId, String kind);

    // Previous runs (keyset paging by created_at): everyone's runs, or only the caller's.
    List<RecommendationAnalysisRun> findByKindAndCreatedAtBeforeOrderByCreatedAtDesc(
            String kind, Instant before, Pageable page);

    List<RecommendationAnalysisRun> findByKindAndSubjectIdIgnoreCaseAndCreatedAtBeforeOrderByCreatedAtDesc(
            String kind, String subjectId, Instant before, Pageable page);

    List<RecommendationAnalysisRun> findByKindAndRequestedByAndCreatedAtBeforeOrderByCreatedAtDesc(
            String kind, Long requestedBy, Instant before, Pageable page);

    List<RecommendationAnalysisRun> findByKindAndRequestedByAndSubjectIdIgnoreCaseAndCreatedAtBeforeOrderByCreatedAtDesc(
            String kind, Long requestedBy, String subjectId, Instant before, Pageable page);
}
