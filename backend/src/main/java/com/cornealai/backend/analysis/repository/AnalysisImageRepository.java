package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.AnalysisImage;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface AnalysisImageRepository extends JpaRepository<AnalysisImage, UUID> {

    java.util.List<AnalysisImage> findByDonorCaseIdOrderByCreatedAtDesc(UUID donorCaseId);

    long countByDonorCaseId(UUID donorCaseId);
}
