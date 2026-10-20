package com.cornealai.backend.security;

/**
 * Fine-grained permissions granted to roles on the server side.
 * The authority string is what {@code @PreAuthorize("hasAuthority(...)")} checks against.
 */
public enum Permission {

    USERS_READ("users:read"),
    USERS_MANAGE("users:manage"),
    ROLES_ASSIGN("roles:assign"),
    ANALYSIS_RUN("analysis:run"),
    /** Confirm a case's grade and findings (specialist sign-off). */
    CASE_SIGNOFF("case:signoff"),
    /** Read and record serology results, and list sign-off candidates (which carry serology status). */
    SEROLOGY_ACCESS("serology:access"),
    /** Read the audit log of who decrypted or changed what. */
    AUDIT_READ("audit:read");

    private final String authority;

    Permission(String authority) {
        this.authority = authority;
    }

    public String authority() {
        return authority;
    }
}
