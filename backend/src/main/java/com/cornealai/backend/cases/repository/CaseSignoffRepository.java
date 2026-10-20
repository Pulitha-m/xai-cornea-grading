package com.cornealai.backend.cases.repository;

import com.cornealai.backend.cases.entity.CaseSignoff;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface CaseSignoffRepository extends JpaRepository<CaseSignoff, UUID> {

    List<CaseSignoff> findByDonorCaseIdOrderByCreatedAtDesc(UUID donorCaseId);

    Optional<CaseSignoff> findFirstByDonorCaseIdOrderByCreatedAtDesc(UUID donorCaseId);

    List<CaseSignoff> findAllByOrderByCreatedAtDesc();
}
