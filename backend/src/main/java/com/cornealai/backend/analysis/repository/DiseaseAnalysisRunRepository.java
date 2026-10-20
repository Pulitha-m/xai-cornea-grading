package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.DiseaseAnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface DiseaseAnalysisRunRepository extends JpaRepository<DiseaseAnalysisRun, UUID> {

    List<DiseaseAnalysisRun> findByImageId(UUID imageId);

    List<DiseaseAnalysisRun> findByDonorCaseIdOrderByCreatedAtDesc(UUID donorCaseId);
}
