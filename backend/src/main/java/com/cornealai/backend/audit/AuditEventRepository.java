package com.cornealai.backend.audit;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface AuditEventRepository extends JpaRepository<AuditEvent, UUID> {

    List<AuditEvent> findAllByOrderByOccurredAtDesc(Pageable page);

    List<AuditEvent> findBySubjectIdOrderByOccurredAtDesc(UUID subjectId, Pageable page);
}
