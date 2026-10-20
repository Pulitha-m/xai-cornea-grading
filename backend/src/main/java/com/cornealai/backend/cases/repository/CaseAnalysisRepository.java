package com.cornealai.backend.cases.repository;

import com.cornealai.backend.cases.entity.CaseAnalysis;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface CaseAnalysisRepository extends JpaRepository<CaseAnalysis, UUID> {
}
