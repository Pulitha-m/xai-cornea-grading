package com.cornealai.backend.audit;

import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.repository.AppUserRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Append-only record of who decrypted or changed sensitive data. A failure to record is not swallowed:
 * the action it guards fails too, so nothing is decrypted without a trace.
 */
@Service
public class AuditService {

    /** Audited actions. */
    public static final String CASE_VIEW = "CASE_VIEW";
    public static final String CASE_LIST = "CASE_LIST";
    public static final String CASE_UPDATE = "CASE_UPDATE";
    public static final String IMAGE_VIEW = "IMAGE_VIEW";
    public static final String CASE_ANALYSIS = "CASE_ANALYSIS";
    public static final String RUN_VIEW = "RUN_VIEW";
    public static final String SEROLOGY_VIEW = "SEROLOGY_VIEW";
    public static final String SEROLOGY_UPDATE = "SEROLOGY_UPDATE";
    public static final String SIGNOFF_CREATE = "SIGNOFF_CREATE";
    public static final String SIGNOFF_VIEW = "SIGNOFF_VIEW";
    public static final String CANDIDATES_EXPORT = "CANDIDATES_EXPORT";

    private static final int MAX_LIMIT = 500;

    private final AuditEventRepository events;
    private final AppUserRepository users;

    public AuditService(AuditEventRepository events, AppUserRepository users) {
        this.events = events;
        this.users = users;
    }

    /** {@code detail} must not contain sensitive values (tissue IDs, serology, notes). */
    public void record(Long userId, String action, String subjectType, UUID subjectId, String detail) {
        AuditEvent event = new AuditEvent();
        event.setId(UUID.randomUUID());
        event.setOccurredAt(Instant.now());
        event.setUserId(userId);
        event.setAction(action);
        event.setSubjectType(subjectType);
        event.setSubjectId(subjectId);
        event.setDetail(detail);
        events.save(event);
    }

    public record AuditEntry(UUID id, Instant occurredAt, Long userId, String username, String action,
                             String subjectType, UUID subjectId, String detail) {
    }

    /** Newest first; optionally only the events about one subject (e.g. a case). */
    public List<AuditEntry> recent(Integer limit, UUID subjectId) {
        PageRequest page = PageRequest.of(0, Math.clamp(limit == null ? 100 : limit, 1, MAX_LIMIT));
        List<AuditEvent> found = subjectId == null
                ? events.findAllByOrderByOccurredAtDesc(page)
                : events.findBySubjectIdOrderByOccurredAtDesc(subjectId, page);
        Map<Long, String> names = users.findAllById(found.stream().map(AuditEvent::getUserId).distinct().toList())
                .stream().collect(Collectors.toMap(AppUser::getId, AppUser::getUsername, (a, b) -> a));
        return found.stream().map(e -> new AuditEntry(e.getId(), e.getOccurredAt(), e.getUserId(),
                names.getOrDefault(e.getUserId(), "(deleted user)"), e.getAction(), e.getSubjectType(),
                e.getSubjectId(), e.getDetail())).toList();
    }
}
