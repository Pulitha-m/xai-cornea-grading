package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.AnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface AnalysisRunRepository extends JpaRepository<AnalysisRun, UUID> {

    List<AnalysisRun> findByImageId(UUID imageId);
}
