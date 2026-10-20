package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.CellularAnalysisRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface CellularAnalysisRunRepository extends JpaRepository<CellularAnalysisRun, UUID> {

    List<CellularAnalysisRun> findByImageId(UUID imageId);
}
