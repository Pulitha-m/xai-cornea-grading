package com.cornealai.backend.audit;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

/** The audit log, for administrators: who decrypted or changed what, newest first. */
@RestController
@RequestMapping("/api/audit")
@PreAuthorize("hasAuthority('audit:read')")
public class AuditController {

    private final AuditService audit;

    public AuditController(AuditService audit) {
        this.audit = audit;
    }

    @GetMapping
    public List<AuditService.AuditEntry> recent(@RequestParam(required = false) Integer limit,
                                                @RequestParam(required = false) UUID subjectId) {
        return audit.recent(limit, subjectId);
    }
}
