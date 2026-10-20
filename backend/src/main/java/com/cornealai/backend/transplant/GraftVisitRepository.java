package com.cornealai.backend.transplant;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface GraftVisitRepository extends JpaRepository<GraftVisit, UUID> {

    List<GraftVisit> findByGraftIdOrderByMonth(UUID graftId);

    Optional<GraftVisit> findByGraftIdAndMonth(UUID graftId, int month);
}
