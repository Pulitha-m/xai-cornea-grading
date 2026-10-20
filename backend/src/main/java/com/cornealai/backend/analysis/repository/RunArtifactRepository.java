package com.cornealai.backend.analysis.repository;

import com.cornealai.backend.analysis.entity.RunArtifact;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface RunArtifactRepository extends JpaRepository<RunArtifact, UUID> {

    List<RunArtifact> findByModuleAndRunId(String module, UUID runId);
}
