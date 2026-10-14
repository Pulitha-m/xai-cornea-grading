package com.cornealai.backend.user.entity;

import com.cornealai.backend.security.Permission;

import java.util.Collections;
import java.util.EnumSet;
import java.util.Set;

import static com.cornealai.backend.security.Permission.*;

/**
 * The five application roles and the permissions each one carries.
 * This mapping is the single source of truth for authorization; it is never
 * read from the client or from JWT claims.
 */
public enum RoleName {

    ADMIN(EnumSet.of(USERS_READ, USERS_MANAGE, ROLES_ASSIGN)),
    MANAGER(EnumSet.of(USERS_READ)),
    DOCTOR(EnumSet.of(ANALYSIS_RUN)),
    NURSE(EnumSet.of(ANALYSIS_RUN)),
    SUPPORT_STAFF(EnumSet.noneOf(Permission.class));

    private final Set<Permission> permissions;

    RoleName(Set<Permission> permissions) {
        this.permissions = Collections.unmodifiableSet(permissions);
    }

    public Set<Permission> permissions() {
        return permissions;
    }

    /** Authority checked by {@code hasRole(...)}. */
    public String roleAuthority() {
        return "ROLE_" + name();
    }
}
