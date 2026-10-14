package com.cornealai.backend.security;

/**
 * Fine-grained permissions granted to roles on the server side.
 * The authority string is what {@code @PreAuthorize("hasAuthority(...)")} checks against.
 */
public enum Permission {

    USERS_READ("users:read"),
    USERS_MANAGE("users:manage"),
    ROLES_ASSIGN("roles:assign"),
    ANALYSIS_RUN("analysis:run");

    private final String authority;

    Permission(String authority) {
        this.authority = authority;
    }

    public String authority() {
        return authority;
    }
}
