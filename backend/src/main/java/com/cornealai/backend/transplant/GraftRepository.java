package com.cornealai.backend.transplant;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface GraftRepository extends JpaRepository<Graft, UUID> {

    Optional<Graft> findByDonorCaseId(UUID donorCaseId);

    boolean existsByDonorCaseId(UUID donorCaseId);

    List<Graft> findAllByOrderByCreatedAtDesc();
}
