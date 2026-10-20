package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.RecommendationAnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface RecommendationAnalysisRunRepository extends JpaRepository<RecommendationAnalysisRun, UUID> {

    List<RecommendationAnalysisRun> findBySubjectId(String subjectId);

    List<RecommendationAnalysisRun> findBySubjectIdAndKindOrderByCreatedAtDesc(String subjectId, String kind);
}
