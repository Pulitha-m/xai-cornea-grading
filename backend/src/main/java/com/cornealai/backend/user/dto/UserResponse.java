package com.cornealai.backend.user.dto;

import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;

import java.time.Instant;

public record UserResponse(
        Long id,
        String username,
        String email,
        String fullName,
        RoleName role,
        boolean enabled,
        Instant lastLoginAt,
        Instant createdAt
) {

    public static UserResponse from(AppUser user) {
        return new UserResponse(
                user.getId(),
                user.getUsername(),
                user.getEmail(),
                user.getFullName(),
                user.getRole().getName(),
                user.isEnabled(),
                user.getLastLoginAt(),
                user.getCreatedAt()
        );
    }
}
