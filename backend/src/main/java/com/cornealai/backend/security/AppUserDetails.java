package com.cornealai.backend.security;

import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * Authenticated principal. Authorities are derived from the role stored in the
 * database, never from client-supplied data or token claims.
 */
public class AppUserDetails implements UserDetails {

    private final Long id;
    private final String username;
    private final String passwordHash;
    private final RoleName role;
    private final boolean enabled;
    private final Instant lockedUntil;
    private final List<GrantedAuthority> authorities;

    private AppUserDetails(AppUser user) {
        this.id = user.getId();
        this.username = user.getUsername();
        this.passwordHash = user.getPasswordHash();
        this.role = user.getRole().getName();
        this.enabled = user.isEnabled();
        this.lockedUntil = user.getLockedUntil();

        List<GrantedAuthority> granted = new ArrayList<>();
        granted.add(new SimpleGrantedAuthority(role.roleAuthority()));
        role.permissions().forEach(p -> granted.add(new SimpleGrantedAuthority(p.authority())));
        this.authorities = List.copyOf(granted);
    }

    public static AppUserDetails from(AppUser user) {
        return new AppUserDetails(user);
    }

    public Long getId() {
        return id;
    }

    public RoleName getRole() {
        return role;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public String getUsername() {
        return username;
    }

    @Override
    public boolean isAccountNonLocked() {
        return lockedUntil == null || !lockedUntil.isAfter(Instant.now());
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }
}
