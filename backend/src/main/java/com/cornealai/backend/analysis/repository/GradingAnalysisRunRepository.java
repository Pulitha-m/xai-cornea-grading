package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.GradingAnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface GradingAnalysisRunRepository extends JpaRepository<GradingAnalysisRun, UUID> {

    List<GradingAnalysisRun> findByImageId(UUID imageId);
}
