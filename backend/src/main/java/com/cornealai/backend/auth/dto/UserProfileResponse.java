package com.cornealai.backend.auth.dto;

import com.cornealai.backend.security.Permission;
import com.cornealai.backend.user.entity.AppUser;
import com.cornealai.backend.user.entity.RoleName;

import java.util.List;

/** The signed-in user's identity, role and the permissions derived from it. */
public record UserProfileResponse(
        Long id,
        String username,
        String email,
        String fullName,
        RoleName role,
        List<String> permissions
) {

    public static UserProfileResponse from(AppUser user) {
        RoleName role = user.getRole().getName();
        List<String> permissions = role.permissions().stream()
                .map(Permission::authority)
                .sorted()
                .toList();

        return new UserProfileResponse(
                user.getId(),
                user.getUsername(),
                user.getEmail(),
                user.getFullName(),
                role,
                permissions
        );
    }
}
